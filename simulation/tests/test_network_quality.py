"""보고 오차 축약과 내부 비수렴의 실제 관망 회귀 검사."""
from pathlib import Path
from importlib.util import find_spec
import tempfile
import unittest
import json

from waterleague_sim.engine import network
from waterleague_sim.engine.network_quality import routing_balance
from waterleague_sim.reference.flood_cases import conduit_drainage_case
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError


@unittest.skipUnless(network.library_path().exists(), '관망 엔진 빌드 필요')
class NetworkQualityTests(unittest.TestCase):
    def run_case(self, segments, root):
        model = conduit_drainage_case(segments)
        with network.NetworkSession(model['network']['inputText'], Path(root) / str(segments),
                                    evaluation_seconds=120) as session:
            session.advance(120)
            return session.finish()

    def test_sub_cubic_foot_loss_is_not_certified_by_rounded_engine_error(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_case(1, root)
            self.assertLess(abs(result['routingContinuityPercent']), .00001)
            quality = result['numericalQuality']
            balance = quality['routingBalance']
            self.assertGreater(balance['continuityPercent'], 1)
            self.assertLess(abs(balance['residualM3']), .3048 ** 3)
            self.assertEqual(result['convergence']['nonConvergedSteps'], 0)
            self.assertEqual(quality['failureReasons'], ['ROUTING_VOLUME_RESIDUAL_EXCEEDED'])
            self.assertEqual(result['numericalStatus'], 'FAILED')

    def test_converged_mass_balance_cannot_hide_nonconverged_internal_steps(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_case(5, root)
            quality = result['numericalQuality']
            self.assertLess(abs(quality['routingBalance']['continuityPercent']), 1)
            self.assertGreater(result['convergence']['nonConvergedSteps'], 0)
            self.assertEqual(result['convergence']['routingSteps'], 120000)
            self.assertEqual(quality['failureReasons'], ['ROUTING_NONCONVERGED'])
            self.assertEqual(result['numericalStatus'], 'FAILED')

    def test_signed_boundaries_keep_physical_denominator_and_dry_zero(self):
        keys = network._TOTAL_FIELDS[1:]
        dry = dict.fromkeys(keys, 0.)
        self.assertEqual(routing_balance(dry)['continuityPercent'], 0)
        totals = dry | {'initialStorageM3': 2., 'storageM3': 3.,
                        'externalInflowM3': -1., 'outflowM3': -2.}
        balance = routing_balance(totals)
        self.assertEqual(balance['totalInM3'], 4)
        self.assertEqual(balance['totalOutIncludingStorageM3'], 4)
        self.assertEqual(balance['residualM3'], 0)

    @unittest.skipUnless(find_spec('anuga'), '지표 엔진 설치 필요')
    def test_nonconverged_network_cannot_promote_coupled_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            model = conduit_drainage_case(5)
            model['evaluationMetrics'] = {
                'schemaVersion': 1, 'policyVersion': 'NUMERICAL_QUALITY_REGRESSION_v1',
                'evidence': 'NUMERICAL_TEST_ONLY', 'startMilliseconds': 0,
                'endMilliseconds': 120000, 'networkOutfalls': ['OUT'],
                'exposureTriangles': list(range(len(model['surface']['triangles']))),
                'wetDepthThresholdM': .001}
            output = Path(root) / 'coupled'
            with self.assertRaisesRegex(FloodModelError, 'COUPLED_UNMAPPED_NODE_FLOODING'):
                run_coupled(model, output)
            failure = json.loads((output / 'coupled-failure.json').read_text())
            self.assertGreater(failure['lastNetwork']['convergence']['nonConvergedSteps'], 0)
            self.assertGreater(failure['lastNetwork']['totals']['floodingM3'], 0)
            self.assertFalse((output / 'coupled-result.json').exists())


if __name__ == '__main__':
    unittest.main()
