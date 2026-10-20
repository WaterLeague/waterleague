"""합성 강우는 막힘 비교 엔진 검증 전용이며 운영 관측과 구분."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_initialization_sensitivity import inputs
from test_continuous import model_for
from waterleague_sim.engine import continuous, facilities, initialization
from waterleague_sim.engine import pavement_maintenance as study


def comparison_inputs():
    _, _, pet, prior = inputs()
    model, placement = model_for('PERMEABLE_PAVEMENT', [100, 100]+[0]*8)
    model['facilityDesignSet'] = facilities.design_set(5)
    model['sharedSiteSource'] = {'inflowPolicy': 'DIRECT_RAINFALL_ONLY'}
    model['rainfall']['stationId'] = '108'
    from waterleague_sim.engine.initialization_sensitivity import window
    return model, placement, pet, window(prior, 7)


class PavementMaintenanceTests(unittest.TestCase):
    def test_cistern_catalog_preserves_previous_pavement_comparison_input(self):
        model, placement, pet, _ = comparison_inputs()
        previous = model | {'facilityDesignSet': facilities.design_set(4)}
        self.assertEqual(facilities.catalog(4)['profiles']['PERMEABLE_PAVEMENT'],
                         facilities.catalog(5)['profiles']['PERMEABLE_PAVEMENT'])
        for identifier in ('FRESH', 'DUST_96_G', 'DUST_192_G'):
            old = continuous.input_source(previous, [placement], pet, pavement_scenario=identifier)
            new = continuous.input_source(model, [placement], pet, pavement_scenario=identifier)
            # v5의 미사용 덮개 강우계 정의만 추가되며 시설·강우·수리 입력은 동일하다.
            added = [line for line in new.splitlines() if line.startswith(('WL_NO_RAIN ', 'WL_ZERO '))]
            self.assertEqual(added, ['WL_NO_RAIN VOLUME 0:01 1 TIMESERIES WL_ZERO',
                'WL_ZERO 10/12/2026 00:00:00 0', 'WL_ZERO 10/12/2026 00:01:00 0'])
            self.assertEqual(old.splitlines(), [line for line in new.splitlines() if line not in added])
        forged = model | {'facilityDesignSet': facilities.design_set(5) | {'sha256': '0' * 64}}
        with self.assertRaisesRegex(continuous.SimulationQualityError, 'DESIGN_INVALID'):
            study.validate_request(forged, [placement])

    def test_fixed_measured_states_change_only_pavement_row(self):
        model, placement, pet, prior = comparison_inputs()
        expanded, forcing = initialization.prepend(model, pet, prior)
        original = continuous.input_source(expanded, [placement], forcing)
        rows = []
        for identifier, expected in [('FRESH', 12564.0), ('DUST_96_G', 7632.0),
                                     ('DUST_192_G', 5040.0)]:
            modified = continuous.input_source(
                expanded, [placement], forcing, pavement_scenario=identifier)
            old_lines, new_lines = original.splitlines(), modified.splitlines()
            self.assertEqual(len(old_lines), len(new_lines))
            changed = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0][1], f'PP PAVEMENT 60 0.25 0 {expected} 0')
            rows.append(study.scenario(identifier))
        self.assertEqual([v['dustG'] for v in rows], [0, 96, 192])
        self.assertTrue(all(v['cloggingFactor'] == 0 for v in rows))
        self.assertEqual(study.catalog()['cleaningRecovery']['value'], None)
        self.assertFalse(study.catalog()['rankingEligible'])

    def test_incompatible_facility_source_and_unlisted_recovery_rejected(self):
        model, placement, pet, _ = comparison_inputs()
        for value in ('CLEANED', 'AGE_5_YEARS', '', None, True):
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'SCENARIO_INVALID'):
                study.scenario(value)
        for placements in ([], [placement, placement],
                           [placement | {'facilityType': 'GREEN_ROOF'}]):
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'REQUEST_INVALID'):
                continuous.input_source(model, placements, pet, pavement_scenario='FRESH')
        for changes in (
            {'sharedSiteSource': {'inflowPolicy': 'EXTERNAL_INFLOW_UNKNOWN'}},
            {'facilityDesignSet': facilities.design_set(1)},
        ):
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'REQUEST_INVALID'):
                study.validate_request(model | changes, [placement])

    def test_catalog_replacement_and_duplicate_input_row_rejected(self):
        model, placement, pet, _ = comparison_inputs()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'catalog.json'
            path.write_bytes(study.CATALOG_PATH.read_bytes()+b' ')
            with patch.object(study, 'CATALOG_PATH', path):
                with self.assertRaisesRegex(continuous.SimulationQualityError, 'CATALOG_INVALID'):
                    study.catalog()
        source = continuous.input_source(model, [placement], pet)
        row = next(line for line in source.splitlines() if line.startswith('PP PAVEMENT '))
        for malformed in (source.replace(row, ''), source.replace(row, row+'\n'+row)):
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'INPUT_INVALID'):
                study.apply(malformed, model, [placement], 'FRESH')

    @unittest.skipUnless(continuous.library_path().exists(), 'EPA 연속 엔진 필요')
    def test_native_comparison_keeps_common_forcing_spinup_balance_and_inputs(self):
        model, placement, pet, prior = comparison_inputs()
        before = copy.deepcopy((model, placement, pet, prior))
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)/'comparison'
            report = study.analyze(model, placement, pet, prior, directory)
            self.assertEqual(report['status'], 'SUCCEEDED')
            self.assertFalse(report['rankingEligible'])
            self.assertEqual(len(report['cases']), 3)
            self.assertEqual(len(report['differencesFromFresh']), 2)
            self.assertEqual(report['cleaningRecovery']['status'], 'UNAVAILABLE')
            for case in report['cases']:
                self.assertEqual(case['initialization']['warmupMinutes'], 10080)
                self.assertEqual(case['initialization']['evaluationStart'], model['rainfall']['start'])
                self.assertLessEqual(abs(case['runoffContinuityPercent']), 1)
                data = json.loads((directory/(case['scenario']['id']+'.json')).read_text())
                expected_rain = .2*model['cells'][0]['areaM2']
                expected_inflow = .2*placement['areaM2']
                self.assertAlmostEqual(data['final']['precipitationM3'], expected_rain,
                                       delta=max(1e-5, expected_rain*1e-6))
                self.assertAlmostEqual(data['final']['lidInflowM3'], expected_inflow,
                                       delta=max(1e-5, expected_inflow*1e-6))
                self.assertEqual(len(data['samples']), 10)
            manifest = json.loads((directory/'manifest.json').read_text())
            for relative, digest in manifest.items():
                self.assertEqual(hashlib.sha256((directory/relative).read_bytes()).hexdigest(), digest)
            expanded, forcing = initialization.prepend(model, pet, prior)
            plain = continuous.replay(expanded, [], Path(root)/'unchanged', 'baseline', forcing)
            self.assertEqual((directory/'baseline.inp').read_bytes(),
                             (Path(root)/'unchanged/baseline.inp').read_bytes())
            self.assertEqual((directory/'baseline.out').read_bytes(),
                             (Path(root)/'unchanged/baseline.out').read_bytes())
            self.assertEqual(plain['warnings'], 0)
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'OUTPUT_EXISTS'):
                study.analyze(model, placement, pet, prior, directory)
        self.assertEqual((model, placement, pet, prior), before)

    @unittest.skipUnless(continuous.library_path().exists(), 'EPA 연속 엔진 필요')
    def test_failed_native_case_never_yields_zero_or_complete_comparison(self):
        model, placement, pet, prior = comparison_inputs()
        original = continuous.replay

        def replay(*args, **kwargs):
            if kwargs.get('pavement_scenario') == 'DUST_96_G':
                raise continuous.SimulationQualityError('LIVE_NUMERICAL_QUALITY_FAILED')
            return original(*args, **kwargs)

        with tempfile.TemporaryDirectory() as root, patch.object(continuous, 'replay', side_effect=replay):
            report = study.analyze(model, placement, pet, prior, Path(root))
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertIsNone(report['differencesFromFresh'])
            failed = report['cases'][1]
            self.assertEqual(failed['status'], 'FAILED')
            self.assertNotIn('metrics', failed)


if __name__ == '__main__':
    unittest.main()
