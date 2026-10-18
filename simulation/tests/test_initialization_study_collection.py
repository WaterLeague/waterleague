"""보관 강우 우선 사용과 원문 불일치의 재조회 우회 방지."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import analyze_initialization_sensitivity as command


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
