"""이용조 초기 저류의 원 엔진 적용과 운전별 선행 상태 비교 검사."""
import copy
import ctypes as C
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_cistern_game import fixture
from test_initialization_sensitivity import inputs
from waterleague_sim.engine import cistern_initialization as study, cistern_demand, continuous, swmm


def setup():
    model, placement = fixture([0] * 10)
    common, _, pet, prior = inputs()
    model['rainfall'].update(stationId=common['rainfall']['stationId'], sourceHashes=['SYNTHETIC_TEST_ONLY'])
    return model, placement, pet, prior


class CisternInitializationTests(unittest.TestCase):
    def test_native_empty_half_full_states_and_unchanged_epa_output(self):
        model, placement, _, _ = setup()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for seed in (0, 50, 100):
                for scenario in (None, cistern_demand.IDENTIFIER):
                    changed = copy.deepcopy(model)
                    changed['hydrology']['initialSaturationPercent'] = seed
                    label = f'seed_{seed}_' + ('demand' if scenario else 'natural')
                    value = continuous.replay(changed, [placement], root, label, cistern_scenario=scenario)
                    self.assertAlmostEqual(value['initial']['lidStorageM3'], 2.35 * seed / 100, places=10)
                    self.assertAlmostEqual(value['initial']['initialStorageM3'], 2.35 * seed / 100, places=10)
                    final = value['final']
                    self.assertLessEqual(abs(final['balanceResidualM3']), max(1e-8, .01 * final['initialStorageM3']))
                    if seed:
                        self.assertGreater(final['lidDrainageTotalM3'], 0)
                    library = C.CDLL(str(swmm.library_path()))
                    self.assertEqual(library.swmm_run(os.fsencode(root / (label + '.inp')),
                        os.fsencode(root / 'original.rpt'), os.fsencode(root / 'original.out')), 0)
                    self.assertEqual((root / 'original.out').read_bytes(), (root / (label + '.out')).read_bytes())
            zero = (root / 'seed_0_natural.inp').read_text()
            self.assertIn('WL_TANK WL_RB 1 2.35 0 0 100 0 * OUT 0', zero)
            for seed in (-1, 101, True, float('nan'), float('inf'), None):
                model['hydrology']['initialSaturationPercent'] = seed
                with self.assertRaises(swmm.SimulationQualityError):
                    continuous.input_source(model, [placement], None)

    def test_seven_day_storage_memory_and_fourteen_day_drawdown_are_separate_by_operation(self):
        model, placement, pet, prior = setup()
        original = copy.deepcopy((model, placement, pet, prior))
        with tempfile.TemporaryDirectory() as root:
            report = study.analyze(model, placement, pet, prior, root, days=(7, 14))
            self.assertEqual(report['status'], 'SUCCEEDED')
            self.assertEqual(len(report['cases']), 8)
            by = {(c['operation'], c['days'], c['seedSaturationPercent']): c for c in report['cases']}
            dry = by['LITERATURE_DEMAND', 7, 0]
            wet = by['LITERATURE_DEMAND', 7, 100]
            self.assertEqual(dry['nativeSeedStorageM3'], 0)
            self.assertAlmostEqual(wet['nativeSeedStorageM3'], 2.35)
            # 첫 엔진 시작 단계 한 개의 인출량 이내에서 연속시간 해와 대조한다.
            self.assertAlmostEqual(wet['tank']['initialStorageM3'], 2.35 - 7 * .201, delta=.201 / 86400)
            self.assertAlmostEqual(wet['demand']['suppliedM3'], .201 * 600 / 86400, places=10)
            self.assertEqual(dry['demand']['suppliedM3'], 0)
            self.assertGreater(dry['demand']['unmetDemandM3'], 0)
            self.assertLess(by['LITERATURE_DEMAND', 14, 100]['tank']['initialStorageM3'], 1e-8)
            for day in (7, 14):
                for seed in (0, 100):
                    self.assertIsNone(by['NATURAL_DRAIN', day, seed]['demand'])
                    self.assertLess(by['NATURAL_DRAIN', day, seed]['tank']['initialStorageM3'], 1e-8)
            comparison = next(c for c in report['comparisons'] if c['operation'] == 'LITERATURE_DEMAND')['comparison']
            self.assertGreater(comparison['seedDifferences'][0]['wetMinusDry']['initialLidStorageM3'], .94)
            self.assertLess(abs(comparison['seedDifferences'][1]['wetMinusDry']['initialLidStorageM3']), 1e-8)
            self.assertEqual((model, placement, pet, prior), original)
            manifest = json.loads((Path(root) / 'manifest.json').read_text())
            self.assertIn('cistern-demand.json', manifest)
            for case in report['cases']:
                trace = json.loads((Path(root) / (case['label'] + '.json')).read_text())
                self.assertEqual(len(trace['samples']), 10)
                self.assertEqual(trace['initial']['at'], model['rainfall']['start'])
                self.assertTrue(case['initialization']['scoreExcludesWarmup'])
                self.assertEqual(case['inputSha256'], manifest[case['label'] + '.inp'])

    def test_failed_condition_holds_only_that_operating_comparison(self):
        model, placement, pet, prior = setup()
        original = continuous.replay
        def replay(*args, **kwargs):
            if args[3] == 'literature_demand_7d_100':
                raise swmm.SimulationQualityError('LIVE_NUMERICAL_QUALITY_FAILED')
            return original(*args, **kwargs)
        with tempfile.TemporaryDirectory() as root, patch.object(continuous, 'replay', side_effect=replay):
            report = study.analyze(model, placement, pet, prior, root)
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertEqual([c['comparison']['status'] for c in report['comparisons']],
                ['MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD', 'INCOMPLETE'])
            self.assertIsNone(report['comparisons'][1]['comparison']['ranges'])
            self.assertNotIn('metrics', report['cases'][-1])

    def test_ignored_full_seed_is_rejected_instead_of_claiming_convergence(self):
        model, placement, pet, prior = setup()
        original = continuous.replay
        def replay(*args, **kwargs):
            changed = copy.deepcopy(args[0])
            changed['hydrology']['initialSaturationPercent'] = 0
            return original(changed, *args[1:], **kwargs)
        with tempfile.TemporaryDirectory() as root, patch.object(continuous, 'replay', side_effect=replay):
            report = study.analyze(model, placement, pet, prior, root)
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertTrue(all(c.get('errorCode') == 'CISTERN_SPINUP_SEED_NOT_APPLIED'
                for c in report['cases'] if c['seedSaturationPercent'] == 100))
            self.assertTrue(all(c['comparison']['status'] == 'INCOMPLETE' for c in report['comparisons']))

    def test_invalid_facility_version_or_duration_does_not_start_native_run(self):
        model, placement, pet, prior = setup()
        with tempfile.TemporaryDirectory() as root, patch.object(continuous, 'replay') as native:
            for kwargs in ({'schema_version': 1}, {'schema_version': True}, {'days': (14, 7)}, {'days': (8,)}):
                with self.assertRaises(swmm.SimulationQualityError):
                    study.analyze(model, placement, pet, prior, root, **kwargs)
            with self.assertRaises(swmm.SimulationQualityError):
                study.analyze(model, placement | {'facilityType': 'GREEN_ROOF'}, pet, prior, root)
            native.assert_not_called()

    def test_worker_rejects_mismatched_facility_and_comparison_policy_before_engine(self):
        from waterleague_sim import run_historical_job as worker
        from waterleague_sim.engine.initialization_sensitivity import encode
        model, placement, _, _ = setup()
        mismatches = (
            ('RAINWATER_CISTERN', 'SELECTED_SURFACE_7_DAY_DRY_WET_V1'),
            ('RAINWATER_CISTERN', 'SELECTED_SWALE_7_DAY_STATE_V2'),
            ('GREEN_ROOF', 'SELECTED_CISTERN_7_DAY_STORAGE_V3'),
            ('VEGETATIVE_SWALE', 'SELECTED_CISTERN_7_DAY_STORAGE_V3'),
        )
        with tempfile.TemporaryDirectory() as root, patch.object(worker, 'forcing', return_value=encode(model)), \
                patch.object(worker, 'load_climate') as climate, patch.object(worker, 'experiment') as native:
            for facility, policy in mismatches:
                raw = json.dumps([placement | {'districtId': 'TEST_ONLY',
                    'facilityType': facility, 'initializationSensitivity': policy}])
                request = {'modelHash': 'test-only', 'placements': raw,
                    'inputHash': continuous.digest(('test-only\n' + raw).encode())}
                with self.assertRaisesRegex(ValueError, 'HISTORICAL_SENSITIVITY_INVALID'):
                    worker.calculate(request, Path(root))
            climate.assert_not_called()
            native.assert_not_called()


if __name__ == '__main__':
    unittest.main()
