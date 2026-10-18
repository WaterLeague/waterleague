"""이용조의 관측 초기 상태·수지 보존·실패 효과 보류·재생 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine import facility_metrics
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.initialized_cistern import (
    comparison, prepare_initialized_cistern, run_initialized_cistern,
)
from waterleague_sim.engine.network import sha256
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.cistern_network import design
from waterleague_sim.reference.initialized_facilities import inputs

ROOT = Path(__file__).resolve().parents[2]


def request(days=7, seed=0):
    model, spec, init = inputs(days)
    placement = design(model['inputText'].encode()) | {'schemaVersion': 2, 'initialDepthM': seed}
    return model, spec, init, placement


class InitializedCisternInputTests(unittest.TestCase):
    def test_original_binding_covers_before_forcing_and_preserves_area_and_ground(self):
        args = request()
        original = deepcopy(args)
        prepared, raw, metadata = prepare_initialized_cistern(*args)
        self.assertEqual(args, original)
        source = records(prepared.model['inputText'].encode())[1]
        target = records(raw)[1]
        areas = lambda sections: sum(float(r['tokens'][3])*10000 for r in sections['SUBCATCHMENTS'])
        self.assertAlmostEqual(areas(source), areas(target), places=8)
        self.assertEqual(next(r['tokens'] for r in target['INFILTRATION'] if r['tokens'][0] == 'S1'),
                         source['INFILTRATION'][0]['tokens'])
        self.assertEqual(metadata['originalDesign'], args[3])
        self.assertEqual(metadata['sourceNetworkSha256'], prepared.summary['derivedSha256'])
        self.assertEqual(metadata['catchmentPartition']['preservedPerviousAreaM2'], 4000)
        self.assertEqual(metadata['catchmentPartition']['coverRainfallRoute'],
                         'BYPASS_CATCHMENT_TO_ORIGINAL_OUTLET')
        stale = args[3] | {'sourceNetworkSha256': '0'*64}
        with self.assertRaisesRegex(FloodModelError, 'SOURCE_BINDING_INVALID'):
            prepare_initialized_cistern(*args[:3], stale)
        changed = args[0] | {'inputText': args[0]['inputText'].replace('TANK 0 10', 'TANK 0 9')}
        with self.assertRaisesRegex(FloodModelError, 'SOURCE_BINDING_INVALID'):
            prepare_initialized_cistern(changed, *args[1:])
        unsupported = args[0] | {'inputText': args[0]['inputText'].replace('WET_STEP 00:00:01', 'WET_STEP 00:00:10')}
        rebound = design(unsupported['inputText'].encode()) | {'schemaVersion': 2}
        with self.assertRaisesRegex(FloodModelError, 'SECOND_HYDROLOGY_REQUIRED'):
            prepare_initialized_cistern(unsupported, *args[1:3], rebound)


@unittest.skipUnless(facility_metrics.library_path().exists(), '관망 첨두 엔진 설치 필요')
class InitializedCisternNativeTests(unittest.TestCase):
    def test_observed_dry_wet_periods_exact_replay_and_withheld_failure(self):
        target = os.environ.get('INITIALIZED_CISTERN_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            self.assertFalse(root.exists())
            root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='cistern-initial-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        results = {}
        for name, days, seed in (('7d-dry', 7, 0), ('7d-wet', 7, 1.4),
                                 ('14d-dry', 14, 0), ('14d-wet', 14, 1.4), ('replay-14d-dry', 14, 0)):
            result = results[name] = run_initialized_cistern(*request(days, seed), root/name)
            print(name, result['numericalStatus'], flush=True)
            self.assertEqual(result['numericalStatus'], 'PASSED', result['comparison'])
            self.assertFalse(result['rankingEligible'])
            self.assertEqual(result['initialization']['stations'][0]['evaluationDepthMm'], 85)
            self.assertEqual(result['strategyEvaluation']['startSeconds'], days*86400)
            self.assertEqual(result['comparison']['sourceRunoffPreservation']['status'], 'PASSED')
            self.assertLessEqual(abs(result['comparison']['sourceRunoffPreservation']['differenceM3']), 1e-7)
            node = result['evaluationInitialStorage']
            self.assertGreater(node['storageM3'], 0)
            self.assertNotAlmostEqual(node['depthM'], seed, places=6)
            whole = result['storage']['wholeRunLedger']['facilities'][0]
            evaluated = result['storage']['evaluationLedger']['facilities'][0]
            self.assertLess(evaluated['inflowM3'], whole['inflowM3'])
            self.assertEqual(evaluated['initialStorageM3'], node['storageM3'])
            self.assertEqual(evaluated['floodingM3'], 0)
            for scenario in ('baseline', 'strategy'):
                network = json.loads((root/name/scenario/'network-result.json').read_bytes())
                self.assertEqual(network['convergence']['nonConvergedSteps'], 0)
                self.assertEqual(network['evaluationMetrics']['combined']['coveredSeconds'], 359*60)
                self.assertGreaterEqual(network['evaluationMetrics']['combined']['peakOutwardTimeSeconds'], days*86400)
        a, b = results['14d-dry'], results['replay-14d-dry']
        for key in ('comparison', 'baselineEvaluation', 'strategyEvaluation', 'storage', 'evaluationInitialStorage'):
            self.assertEqual(a[key], b[key])
        for scenario in ('baseline', 'strategy'):
            self.assertEqual(sha256(root/'14d-dry'/scenario/'network.out'),
                             sha256(root/'replay-14d-dry'/scenario/'network.out'))
        base_result = json.loads((root/'14d-dry/baseline/network-result.json').read_bytes())
        strategy_result = json.loads((root/'14d-dry/strategy/network-result.json').read_bytes())
        failed = comparison(a['baselineEvaluation'], a['strategyEvaluation'],
            a['storage'] | {'numericalStatus': 'FAILED'}, base_result, strategy_result)
        self.assertIsNone(failed['effects'])
        self.assertEqual(failed['rawChanges'], a['comparison']['rawChanges'])
        bad = deepcopy(a['strategyEvaluation'])
        bad['routingTotals']['runoffInflowM3'] -= 10
        self.assertEqual(comparison(a['baselineEvaluation'], bad, a['storage'], base_result,
                         strategy_result)['effectStatus'], 'WITHHELD_NUMERICAL_FAILURE')
        shifted = a['strategyEvaluation'] | {'startSeconds': 0}
        with self.assertRaisesRegex(FloodModelError, 'COMPARISON_WINDOW_MISMATCH'):
            comparison(a['baselineEvaluation'], shifted, a['storage'], base_result, strategy_result)
        args = request()
        overflow = run_initialized_cistern(*args[:3], args[3] | {'captureAreaM2': 8000}, root/'undersized')
        self.assertEqual(overflow['numericalStatus'], 'FAILED')
        self.assertIsNone(overflow['comparison']['effects'])
        self.assertGreater(overflow['storage']['evaluationLedger']['facilities'][0]['floodingM3'], 0)
        results['undersized'] = overflow
        (root/'summary.json').write_text(json.dumps({
            'classification': 'OBSERVED_WEATHER_SYNTHETIC_NETWORK', 'rankingEligible': False,
            'cases': {name: {'comparison': r['comparison'], 'initialStorage': r['evaluationInitialStorage'],
                'storage': r['storage']['evaluationLedger']} for name, r in results.items()},
            'exactNativeReplay': True}, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()
