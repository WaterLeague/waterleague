"""합성 입력은 엔진 수치 시험 전용이며 관측·게임 성과로 사용하지 않는다."""
import copy
import ctypes as C
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from waterleague_sim.engine import continuous, swmm


def model_for(facility, rain):
    model = json.loads((swmm.ROOT/'data/models/seongsu-lab.json').read_text())
    model['cells'] = [next(c for c in model['cells'] if facility in c['allowedTypes'])]
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    model['rainfall'] = {'start': start.isoformat(), 'end': (start+timedelta(minutes=len(rain))).isoformat(),
                        'intervalSeconds': 60, 'depthsMm': rain, 'evidence': 'SYNTHETIC_TEST_ONLY'}
    placement = {'cellId': model['cells'][0]['id'], 'facilityType': facility,
                 'areaM2': model['cells'][0]['maxAreaM2']}
    return model, placement


@unittest.skipUnless(continuous.library_path().exists(), '상태 관측 엔진 빌드 필요')
class ContinuousTests(unittest.TestCase):
    def test_observer_does_not_change_epa_output_and_full_replay_preserves_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            model, placement = model_for('GREEN_ROOF', [1]*120+[0]*60)
            result = continuous.replay(model, [placement], d, 'observed')
            path = Path(d)
            lib = C.CDLL(str(swmm.library_path()))
            try:
                self.assertEqual(lib.swmm_open(os.fsencode(path/'observed.inp'),
                    os.fsencode(path/'original.rpt'), os.fsencode(path/'original.out')), 0)
                self.assertEqual(lib.swmm_start(1), 0)
                elapsed = C.c_double()
                for _ in range(180*6):
                    self.assertEqual(lib.swmm_step(C.byref(elapsed)), 0)
                self.assertEqual(lib.swmm_end(), 0)
                self.assertEqual(lib.swmm_report(), 0)
            finally:
                lib.swmm_close()
            self.assertEqual((path/'original.out').read_bytes(), (path/'observed.out').read_bytes())
            def continuity(p):
                return p.read_text().split('Runoff Quantity Continuity')[1].split('Continuity Error (%)')[0]
            self.assertEqual(continuity(path/'original.rpt'), continuity(path/'observed.rpt'))
            shorter, _ = model_for('GREEN_ROOF', [1]*90)
            prefix = continuous.replay(shorter, [placement], d, 'prefix')
            self.assertEqual(prefix['samples'], result['samples'][:90])
            self.assertGreater(result['samples'][119]['soilMoisture'], result['initial']['soilMoisture'])
            self.assertGreater(result['final']['lidDrainageTotalM3'], 0)

    def test_rain_drydown_overflow_and_zero_rain_for_all_facilities(self):
        with tempfile.TemporaryDirectory() as d:
            for facility in ('RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF'):
                model, placement = model_for(facility, [3]*120+[0]*240)
                result = continuous.experiment(model, placement, Path(d)/facility)
                final = result['strategy']['final']
                self.assertGreater(final['lidSurfaceRunoffM3']+final['lidDrainageTotalM3'], 0)
                self.assertLess(abs(final['balanceResidualM3']), .01*(final['precipitationM3']+final['initialStorageM3']))
                self.assertAlmostEqual(sum(v['incrementM3'] for v in result['contribution']),
                                       result['contribution'][-1]['cumulativeM3'], places=10)
                self.assertLess(final['surfaceDepthMm'], result['strategy']['samples'][119]['surfaceDepthMm'])
            dry, placement = model_for('GREEN_ROOF', [0]*60)
            result = continuous.experiment(dry, placement, Path(d)/'dry')
            self.assertEqual(result['contribution'][-1]['cumulativeM3'], 0)
            self.assertEqual(result['strategy']['final']['soilMoisture'], result['strategy']['initial']['soilMoisture'])

    def test_time_varying_evaporation_changes_moisture_without_reset(self):
        model, placement = model_for('GREEN_ROOF', [0]*1440)
        model['hydrology']['initialSaturationPercent'] = 50
        pet = {'method': 'SYNTHETIC_TEST_ONLY', 'sourceHashes': ['test'],
               'ratesMmDay': [0]*720+[5]*720}
        with tempfile.TemporaryDirectory() as d:
            wet = continuous.replay(model, [placement], d, 'wet', pet)
            dry = continuous.replay(model, [placement], d, 'dry')
            self.assertEqual(wet['samples'][:719], dry['samples'][:719])
            self.assertGreater(wet['final']['evaporationM3'], 0)
            self.assertLess(wet['final']['soilMoisture'], dry['final']['soilMoisture'])
            broken = copy.deepcopy(model)
            broken['rainfall']['depthsMm'][1] = None
            with self.assertRaises(swmm.SimulationQualityError):
                continuous.replay(broken, [placement], d, 'missing')


if __name__ == '__main__':
    unittest.main()
