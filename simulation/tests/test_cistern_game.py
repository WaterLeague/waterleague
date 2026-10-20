"""합성 강우는 엔진 시험 전용. 게임에는 보관 관측 입력을 사용한다."""
import copy
import tempfile
import unittest
from pathlib import Path

from test_continuous import model_for
from waterleague_sim.engine import continuous, swmm
from waterleague_sim.spatial.cistern_game import rules, TYPE


def fixture(rain, area=235):
    model, placement = model_for('GREEN_ROOF', rain)
    model['facilityDesignSet'] = rules()['facilityDesignSet']
    model['sharedSiteSource'] = {'inflowPolicy': 'DIRECT_RAINFALL_ONLY'}
    cell = model['cells'][0]
    cell.update(areaM2=470.125, maxAreaM2=470.125, allowedTypes=['GREEN_ROOF', TYPE])
    placement.update(facilityType=TYPE, areaM2=area)
    return model, placement


class CisternGameTests(unittest.TestCase):
    def test_partial_and_full_roof_keep_rainfall_and_account_for_storage_drain_and_overflow(self):
        with tempfile.TemporaryDirectory() as root:
            for area in (235, 470.125):
                with self.subTest(area=area):
                    model, placement = fixture([2] * 30 + [0] * 90, area)
                    value = continuous.experiment(model, placement, Path(root) / str(area))
                    final = value['strategy']['final']
                    cistern = value['cistern']
                    self.assertAlmostEqual(final['precipitationM3'],
                        value['baseline']['final']['precipitationM3'], places=7)
                    self.assertAlmostEqual(final['precipitationM3'], 470.125 * .06, places=4)
                    self.assertLess(abs(final['balanceResidualM3']), .01 * final['precipitationM3'])
                    self.assertLessEqual(cistern['finalStorageM3'], cistern['capacityM3'] + 1e-6)
                    self.assertGreater(cistern['overflowM3'], 0)
                    self.assertGreater(cistern['drainageM3'], 0)
                    self.assertIsNone(cistern['reuseM3'])
                    self.assertAlmostEqual(cistern['inflowM3'], cistern['overflowM3']
                        + cistern['drainageM3'] + cistern['finalStorageM3'], delta=.001)
                    self.assertLess(abs(value['contribution'][-1]['cumulativeM3']), .001)
                    detention = value['runoffComparison']['detention']
                    self.assertEqual(detention['status'], 'COMPARABLE')
                    self.assertGreater(detention['centroidDelaySeconds'], 0)

    def test_dry_run_and_extended_replay_do_not_invent_effect_or_reset_tank(self):
        with tempfile.TemporaryDirectory() as root:
            model, placement = fixture([0] * 60)
            dry = continuous.experiment(model, placement, Path(root) / 'dry')
            self.assertEqual(dry['contribution'][-1]['cumulativeM3'], 0)
            self.assertEqual(dry['cistern']['finalStorageM3'], 0)
            self.assertEqual(dry['runoffComparison']['detention']['status'], 'UNAVAILABLE')
            self.assertIsNone(dry['runoffComparison']['detention']['centroidDelaySeconds'])
            short, placement = fixture([1] * 60)
            long, _ = fixture([1] * 60 + [0] * 60)
            a = continuous.replay(short, [placement], root, 'short')
            b = continuous.replay(long, [placement], root, 'long')
            self.assertEqual(a['samples'], b['samples'][:60])
            self.assertGreater(a['final']['lidStorageM3'], b['final']['lidStorageM3'])

    def test_invalid_roof_area_foreign_cell_or_unbound_design_is_rejected(self):
        model, placement = fixture([1] * 2)
        with tempfile.TemporaryDirectory() as root:
            for update in ({'areaM2': 471}, {'areaM2': True}, {'cellId': 'other'}):
                with self.subTest(update=update), self.assertRaises(swmm.SimulationQualityError):
                    continuous.replay(model, [placement | update], root, 'invalid')
            for update in ({'kind': 'GROUND'}, {'allowedTypes': ['GREEN_ROOF']}):
                changed = copy.deepcopy(model)
                changed['cells'][0].update(update)
                with self.assertRaises(swmm.SimulationQualityError):
                    continuous.replay(changed, [placement], root, 'invalid')


if __name__ == '__main__':
    unittest.main()
