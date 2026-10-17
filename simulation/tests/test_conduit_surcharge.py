"""공식 압력 해법·실제 적용 설정·빈 시설의 월류/재유입 검사."""
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine import network
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.reference.flood_cases import (
    coupled_case, conduit_drainage_case, coupled_conduit_surcharge_case, tank_input)


@unittest.skipUnless(network.library_path().exists(), '관망 엔진 빌드 필요')
class ConduitSurchargeTests(unittest.TestCase):
    def test_native_settings_distinguish_defaults_from_explicit_si_values(self):
        with tempfile.TemporaryDirectory() as root:
            with network.NetworkSession(tank_input(), Path(root) / 'default', evaluation_seconds=120) as s:
                defaults = s.configuration
                self.assertEqual(defaults['surchargeMethod'], 'EXTRAN')
                self.assertIn('SURCHARGE_METHOD', defaults['defaultedInputOptions'])
                self.assertAlmostEqual(defaults['headConvergenceToleranceM'], .005 * .3048)
                self.assertGreater(defaults['minimumNumericalNodeAreaM2'], 1)
            model = conduit_drainage_case(surcharge_method='SLOT')
            with network.NetworkSession(model['network']['inputText'], Path(root) / 'explicit',
                                        evaluation_seconds=120) as s:
                self.assertEqual(s.configuration['defaultedInputOptions'], [])
                self.assertEqual(s.configuration['surchargeMethod'], 'SLOT')
                self.assertEqual(s.configuration['maximumTrials'], 200)
                self.assertAlmostEqual(s.configuration['minimumNumericalNodeAreaM2'], .01)
                self.assertAlmostEqual(s.configuration['headConvergenceToleranceM'], .000001)
                self.assertEqual(s.configuration['minimumRoutingStepSeconds'], .001)
                s.advance(120)
                result = s.finish()
                self.assertEqual(result['numericalStatus'], 'PASSED')
                self.assertEqual(result['numericalConfiguration'], s.configuration)
                self.assertEqual(result['convergence']['nonConvergedSteps'], 0)

    def test_si_and_us_native_configuration_uses_metres(self):
        with tempfile.TemporaryDirectory() as root:
            inp = conduit_drainage_case(surcharge_method='SLOT')['network']['inputText']
            inp = inp.replace('FLOW_UNITS CMS', 'FLOW_UNITS CFS')
            with network.NetworkSession(inp, Path(root) / 'us', evaluation_seconds=120) as s:
                self.assertAlmostEqual(s.configuration['minimumNumericalNodeAreaM2'], .01 * .3048 ** 2)
                self.assertAlmostEqual(s.configuration['headConvergenceToleranceM'], .000001 * .3048)

    def test_wet_start_failure_is_preserved_without_automatic_method_switch(self):
        with tempfile.TemporaryDirectory() as root:
            original = coupled_case(conduit=True)['network']['inputText']
            for method in ('EXTRAN', 'SLOT'):
                inp = original.replace('FLOW_ROUTING DYNWAVE',
                                       f'FLOW_ROUTING DYNWAVE\nSURCHARGE_METHOD {method}')
                with network.NetworkSession(inp, Path(root) / method, evaluation_seconds=120) as s:
                    s.advance(120)
                    result = s.finish()
                self.assertEqual(result['numericalStatus'], 'FAILED')
                self.assertEqual(result['numericalConfiguration']['surchargeMethod'], method)
                self.assertEqual((Path(root) / method / 'network.inp').read_text(), inp)

    @unittest.skipUnless(find_spec('anuga'), '지표 엔진 설치 필요')
    def test_conduit_surcharge_and_reentry_from_dry_initial_state(self):
        with tempfile.TemporaryDirectory() as root:
            result = run_coupled(coupled_conduit_surcharge_case(), Path(root) / 'coupled')
            self.assertEqual(result['numericalStatus'], 'PASSED')
            self.assertEqual(result['networkNumericalConfiguration']['surchargeMethod'], 'SLOT')
            self.assertEqual(result['networkConvergence']['nonConvergedSteps'], 0)
            balance = result['balance']
            self.assertGreater(balance['networkToSurfaceM3'], .5)
            self.assertGreater(balance['surfaceToNetworkM3'], .5)
            self.assertAlmostEqual(balance['exchangeCancellationResidualM3'], 0, places=12)
            self.assertLess(abs(balance['balanceResidualM3']), .003)
            metrics = result['evaluationMetrics']
            self.assertGreater(metrics['raw']['depthAreaTimeM3Hours'], 0)
            self.assertFalse(metrics['rankingEligible'])


if __name__ == '__main__':
    unittest.main()
