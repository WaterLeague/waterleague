"""전체 선행 상태·평가 창·건조 교환 잔차·재현 일치 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.surface_exchange import DRY_EXCHANGE_POLICY
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.forcing.coupled_initialization import prepare_initialized_coupling, evaluation_ledger
from waterleague_sim.reference.initialized_coupling import inputs
from waterleague_sim.reference.flood_cases import coupled_case
from simulation.tests.test_flood_attribution import policy

ROOT = Path(__file__).resolve().parents[2]
DESIGN = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_text())


class CoupledInitializationContractTests(unittest.TestCase):
    def test_real_sources_common_clock_ownership_and_original_unchanged(self):
        model = inputs(DESIGN)
        original = deepcopy(model)
        prepared = prepare_initialized_coupling(model)
        self.assertEqual(model, original)
        self.assertEqual(prepared.model['durationSeconds'], 7*86400+359*60)
        self.assertEqual(prepared.model['evaluationMetrics']['startMilliseconds'], 7*86400*1000)
        self.assertEqual(prepared.schedule.summary['warmupExpectedRainfallM3'], 2920.)
        self.assertEqual(prepared.schedule.summary['evaluationRainfall']['expectedSurfaceRainfallM3'], 1700.)
        self.assertEqual(prepared.network.summary['stations'][0]['grossEvaluationRainfallM3'], 1700.)
        self.assertEqual(prepared.model['observedRainfall']['stationByTriangle'], [None, None, '421', '421'])
        self.assertNotIn('evaluationMetrics', prepared.model['surface'])

    def test_conflicting_forcing_window_and_missing_prior_rejected(self):
        for change, code in [({'networkForcing': [{'timeMilliseconds': 0}]}, 'EXTERNAL_FORCING_CONFLICT'),
                             ({'durationSeconds': 60}, 'EVALUATION_REQUIRED')]:
            with self.subTest(code=code), self.assertRaisesRegex(FloodModelError, code):
                prepare_initialized_coupling(inputs(DESIGN) | change)
        model = inputs(DESIGN)
        model['observedRainfall']['evaporationReference'] = {'file': 'unbound'}
        with self.assertRaisesRegex(FloodModelError, 'WEATHER_MISMATCH'):
            prepare_initialized_coupling(model)
        with self.assertRaisesRegex(FloodModelError, 'ANTECEDENT_BINDING_INVALID'):
            prepare_initialized_coupling(inputs(DESIGN, days=28))

    def test_dry_exchange_shortfall_is_bounded_and_old_policy_unchanged(self):
        case = coupled_case(initial_network=0)
        model = {'surface': case['surface'], 'ports': case['ports']}
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as temporary:
            root = Path(temporary)
            with EngineProcess('surface_exchange', model, root/'old') as process:
                with self.assertRaisesRegex(FloodModelError, 'SURFACE_OVERDRAW'):
                    process.call('apply_exchange', {'inlet': -1e-12})
            with EngineProcess('surface_exchange', model | {'dryExchangePolicy': DRY_EXCHANGE_POLICY},
                               root/'bounded') as process:
                for _ in range(19):
                    result = process.call('apply_exchange', {'inlet': -5e-10})
                    self.assertEqual(result['transfers'][0]['appliedM3'], 0)
                    self.assertEqual(result['state']['storageM3'], 0)
                self.assertAlmostEqual(result['state']['dryExchangeRoundoff']['withdrawalShortfallM3'], 9.5e-9)
                with self.assertRaisesRegex(FloodModelError, 'BUDGET_EXCEEDED'):
                    process.call('apply_exchange', {'inlet': -9e-10})
            with EngineProcess('surface_exchange', model | {'dryExchangePolicy': DRY_EXCHANGE_POLICY},
                               root/'real-overdraw') as process:
                with self.assertRaisesRegex(FloodModelError, 'SURFACE_OVERDRAW'):
                    process.call('apply_exchange', {'inlet': -2e-9})


class CoupledInitializationNativeTests(unittest.TestCase):
    def test_real_continuous_period_step_replay_baseline_and_failure_propagation(self):
        target = os.environ.get('INITIALIZED_COUPLING_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            self.assertFalse(root.exists())
            root.mkdir(parents=True)
        else:
            temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='initialized-coupling-')
            self.addCleanup(temp.cleanup)
            root = Path(temp.name)
        results, states = {}, {}
        cases = [('7d-60s', 7, 60, DESIGN), ('14d-60s', 14, 60, DESIGN),
                 ('14d-30s', 14, 30, DESIGN), ('replay-7d-60s', 7, 60, DESIGN),
                 ('baseline-7d-60s', 7, 60, None)]
        for name, days, step, design in cases:
            model = inputs(design, days=days, step=step)
            output = root/name
            r = results[name] = run_coupled(model, output)
            n = json.loads((output/'network/network-result.json').read_text())
            s = json.loads((output/'surface/surface-result.json').read_text())
            origin = states[name] = json.loads((output/'evaluation-initial-state.json').read_text())
            final = json.loads((output/'evaluation-final-state.json').read_text())
            self.assertEqual(r['numericalStatus'], 'PASSED', name)
            self.assertEqual(r['initialization']['evaluationLedger']['numericalStatus'], 'PASSED')
            self.assertEqual(r['networkConvergence']['nonConvergedSteps'], 0)
            self.assertEqual(origin['network']['totals']['timeSeconds'], days*86400)
            self.assertGreater(origin['surface']['surface']['storageM3'], 0)
            self.assertGreater(origin['surface']['infiltration']['infiltrationM3'], 0)
            self.assertGreater(origin['ports']['inlet']['surfaceToNetworkM3'], 0)
            ledger = r['initialization']['evaluationLedger']
            self.assertAlmostEqual(ledger['surface']['rainfallM3'], 1700., places=7)
            self.assertLess(ledger['surface']['rainfallM3'], r['balance']['surfaceRainfallM3'])
            self.assertEqual(len(ledger['facilities']['facilities']), 4) if design else self.assertIsNone(ledger['facilities'])
            context = policy()['context'] | {'metricSpecificationSha256': digest(r['evaluationMetrics']['specification']),
                                            'engineSha256': engine_signature(n, s, r)}
            self.assertTrue(read_coupled_record(output, file_digest(output/'coupled-result.json'), context)['complete'])
            if name == '7d-60s':
                altered = deepcopy(final)
                altered['network']['facilities'][0]['inflowM3'] += 1000
                self.assertEqual(evaluation_ledger(origin, altered)['numericalStatus'], 'FAILED')
                changed = deepcopy(r)
                changed['initialization']['evaluationLedger']['surface']['rainfallM3'] += 1
                path, original = output/'coupled-result.json', (output/'coupled-result.json').read_bytes()
                try:
                    path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(EvaluationError, 'INITIALIZATION_LEDGER_MISMATCH'):
                        read_coupled_record(output, file_digest(path), context)
                finally:
                    path.write_bytes(original)
            print(name, r['numericalStatus'], 'steps', r['steps'], flush=True)
        self.assertEqual(states['7d-60s'], states['replay-7d-60s'])
        self.assertEqual(results['7d-60s']['evaluationMetrics'], results['replay-7d-60s']['evaluationMetrics'])
        self.assertEqual((root/'7d-60s/network/network.out').read_bytes(),
                         (root/'replay-7d-60s/network/network.out').read_bytes())
        a, b = results['14d-60s'], results['14d-30s']
        comparison = {'exactReplay': True,
            'step60Minus30': {k: a['evaluationMetrics']['raw'][k]-b['evaluationMetrics']['raw'][k]
                             for k in a['evaluationMetrics']['raw']},
            'period14Minus7InitialSurfaceM3': states['14d-60s']['surface']['surface']['storageM3']
                - states['7d-60s']['surface']['surface']['storageM3'],
            'baselineOutflowM3': results['baseline-7d-60s']['evaluationMetrics']['raw']['outwardVolumeM3']}
        (root/'comparison.json').write_text(json.dumps(comparison, indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()
