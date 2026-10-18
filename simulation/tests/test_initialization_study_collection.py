"""보관 강우 우선 사용과 원문 불일치의 재조회 우회 방지."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import analyze_initialization_sensitivity as command
import package_initialization_study as bundle


def inputs():
    end = datetime(2022, 8, 8, 9, tzinfo=timezone.utc)
    start = end - timedelta(days=7)
    rain = {'start': start.isoformat(), 'end': end.isoformat(), 'stationId': '421',
            'intervalSeconds': 60, 'depthsMm': [0.] * 10080,
            'depthMethods': ['SYNTHETIC_TEST_ONLY'] * 10080, 'reconstructedMinutes': 0,
            'sourceHashes': ['synthetic-rain'], 'sourceRequests': [],
            'qualityWarnings': [], 'aggregatedRainIntervals': [],
            'qualityPolicy': 'SYNTHETIC_TEST_ONLY', 'evidence': 'SYNTHETIC_TEST_ONLY'}
    pet = {'ratesMmDay': [1.] * 10080, 'sourceHashes': ['synthetic-weather'],
           'segments': [], 'sourceRequests': [], 'assumptions': ['SYNTHETIC_TEST_ONLY']}
    prior = {'rainfall': rain, 'evaporation': pet}
    forcing = {k: deepcopy(v) for k, v in rain.items()}
    forcing.update(start=(start-timedelta(days=7)).isoformat(), end=start.isoformat(),
                   observations=[{'depthMm': 0., 'method': 'SYNTHETIC_TEST_ONLY'}] * 10080)
    return prior, forcing, deepcopy(pet)


class InitializationCollectionTests(unittest.TestCase):
    def test_archive_requires_original_facility_source_and_contained_path(self):
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'public.pdf'
            path.write_bytes(b'PUBLIC_TEST_SOURCE')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(bundle.checked_reference('public.pdf', digest, root), path)
            for name, expected in [('public.pdf', '0'*64), ('../public.pdf', digest),
                                   (str(path), digest), ('missing.pdf', digest)]:
                with self.assertRaises(ValueError):
                    bundle.checked_reference(name, expected, root)
            (root/'linked.pdf').symlink_to(path)
            with self.assertRaises(ValueError):
                bundle.checked_reference('linked.pdf', digest, root)

    def test_worker_rejects_mismatched_facility_state_policy_before_any_calculation(self):
        import hashlib
        import json
        import tempfile
        from waterleague_sim import run_historical_job
        for facility, policy in [('VEGETATIVE_SWALE', 'SELECTED_SURFACE_7_DAY_DRY_WET_V1'),
                                 ('GREEN_ROOF', 'SELECTED_SWALE_7_DAY_STATE_V2')]:
            raw = json.dumps([{'facilityType': facility, 'initializationSensitivity': policy}])
            request = {'modelHash': 'test-model', 'placements': raw,
                       'inputHash': hashlib.sha256(('test-model\n'+raw).encode()).hexdigest()}
            with tempfile.TemporaryDirectory() as directory, patch.object(run_historical_job, 'read_catalog',
                    return_value={'test-model': '{}'}):
                target = Path(directory)/'run'
                with self.assertRaisesRegex(ValueError, 'HISTORICAL_SENSITIVITY_INVALID'):
                    run_historical_job.calculate(request, target)
                self.assertFalse(target.exists())

    def test_facility_specific_area_and_bundle_inventory(self):
        site = {'id': 'TEST', 'allowedTypes': ['VEGETATIVE_SWALE'], 'maxAreaM2': 100,
                'areaM2': 100, 'physicalInputs': {'swaleDesign': {'maxAreaM2': 9.99}}}
        _, placement = command.select_placement({'TEST': site}, 'VEGETATIVE_SWALE')
        self.assertEqual(placement['areaM2'], 9.99)
        with self.assertRaisesRegex(ValueError, 'SPINUP_FACILITY_SITE_UNAVAILABLE'):
            command.select_placement({'TEST': site}, 'INFILTRATION_TRENCH')
        summary = {'facilities': ['VEGETATIVE_SWALE'], 'reports': [{'facilityType': 'VEGETATIVE_SWALE'}]}
        self.assertEqual(bundle.study_facilities(summary), ['VEGETATIVE_SWALE'])
        with self.assertRaises(ValueError):
            bundle.study_facilities(summary | {'reports': []})
        with self.assertRaises(ValueError):
            bundle.study_facilities(summary | {'facilities': ['VEGETATIVE_SWALE']*2})
        self.assertEqual(bundle.study_facilities({'reports': [{'facilityType': name}
            for name in bundle.FACILITIES[:3]]}), list(bundle.FACILITIES[:3]))

    def test_complete_archive_does_not_query_rain_even_with_fetch_permission(self):
        prior, forcing, pet = inputs()
        original = deepcopy(prior)
        with patch.object(command, 'archived_forcing', return_value=(forcing, [])), \
                patch.object(command.live, 'observed_forcing') as remote, \
                patch.object(command.live, 'fetch_range'), \
                patch.object(command, 'archived_weather', return_value=pet):
            result = command.extend(prior, 14, 'synthetic-test-token')
        remote.assert_not_called()
        self.assertEqual(len(result['rainfall']['depthsMm']), 20160)
        self.assertEqual(len(result['evaporation']['ratesMmDay']), 20160)
        self.assertEqual(prior, original)

    def test_conflicting_archive_never_falls_back_to_new_response(self):
        prior, _, _ = inputs()
        with patch.object(command, 'archived_forcing', side_effect=
                          command.RainfallQualityError('AWS_OVERLAPPING_RESPONSE_CHANGED')), \
                patch.object(command.live, 'observed_forcing') as remote, \
                patch.object(command.live, 'fetch_range'):
            with self.assertRaisesRegex(command.RainfallQualityError, 'AWS_OVERLAPPING_RESPONSE_CHANGED'):
                command.extend(prior, 14, 'synthetic-test-token')
        remote.assert_not_called()

    def test_missing_archive_requires_explicit_fetch_and_preserves_remote_quality_error(self):
        prior, _, _ = inputs()
        with patch.object(command, 'archived_forcing', side_effect=
                          command.RainfallQualityError('AWS_REQUIRED_MINUTE_MISSING')), \
                patch.object(command.live, 'observed_forcing', side_effect=
                          command.RainfallQualityError('AWS_ROLLING_TOTAL_MISMATCH')) as remote, \
                patch.object(command.live, 'fetch_range'):
            with self.assertRaisesRegex(command.RainfallQualityError, 'AWS_REQUIRED_MINUTE_MISSING'):
                command.extend(prior, 14, '')
            remote.assert_not_called()
            with self.assertRaisesRegex(command.RainfallQualityError, 'AWS_ROLLING_TOTAL_MISMATCH'):
                command.extend(prior, 14, 'synthetic-test-token')
            remote.assert_called_once()


if __name__ == '__main__':
    unittest.main()
