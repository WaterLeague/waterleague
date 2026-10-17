"""신규 침투 경계의 실엔진 수지와 이전 입력 재현 검증."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from waterleague_sim.engine import continuous, facilities
from waterleague_sim.shared_model import resolve, site_catalog


def model(version):
    value, _, _ = resolve({'district_id': '2419953', 'cell_id': 'G1',
                           'model_hash': site_catalog(version)['2419953']['sha256']})
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    value['rainfall'] = {'start': start.isoformat(), 'end': (start+timedelta(days=1)).isoformat(),
                        'intervalSeconds': 60, 'depthsMm': [0]*1440, 'evidence': 'SYNTHETIC_TEST_ONLY'}
    value['hydrology']['initialSaturationPercent'] = 100
    return value


class NativeSoilBoundaryTests(unittest.TestCase):
    def test_new_snapshot_preserves_geometry_and_rejects_changed_boundary(self):
        legacy, current = model(5), model(6)
        cell = current['cells'][0]
        self.assertEqual(cell['coordinates'], legacy['cells'][0]['coordinates'])
        self.assertEqual(cell['maxAreaM2'], legacy['cells'][0]['maxAreaM2'])
        p = {'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20}
        before = continuous.input_source(legacy, [p], None)
        self.assertNotIn('RG STORAGE', before)
        after = continuous.input_source(current, [p], None)
        self.assertIn('RG STORAGE 0 0 3.302 0', after)
        current['cells'][0]['physicalInputs']['rainGardenBoundary']['seepageMmH'] = 999
        with self.assertRaisesRegex(continuous.SimulationQualityError, 'LIVE_NATIVE_SOIL_BOUNDARY_INVALID'):
            continuous.input_source(current, [p], None)
        self.assertEqual(before, continuous.input_source(legacy, [p], None))

    @unittest.skipUnless(continuous.library_path().exists(), 'EPA 연속 엔진 필요')
    def test_native_infiltration_drydown_without_added_storage_or_legacy_change(self):
        legacy, current = model(5), model(6)
        p = {'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20}
        with tempfile.TemporaryDirectory() as root:
            old = continuous.replay(legacy, [p], root, 'legacy')
            result = continuous.experiment(current, p, Path(root)/'current')
            new = result['strategy']
            self.assertEqual(old['final']['infiltrationM3'], 0)
            self.assertEqual(new['initial']['storageM3'], old['initial']['storageM3'])
            self.assertIsNone(new['initial']['storageDepthMm'])
            self.assertGreater(new['final']['infiltrationM3'], 0)
            self.assertLess(new['final']['soilMoisture'], new['initial']['soilMoisture'])
            maximum = 3.302/1000*20*24
            self.assertLessEqual(new['final']['infiltrationM3'], maximum*(1+1e-8))
            self.assertAlmostEqual(new['initial']['storageM3']-new['final']['storageM3'],
                                   new['final']['infiltrationM3'], delta=new['initial']['storageM3']*1e-5)
            self.assertEqual(result['facilityDesign']['nativeSoilBoundary'],
                             current['cells'][0]['physicalInputs']['rainGardenBoundary'])
            self.assertNotIn('nativeSoilBoundary', facilities.evidence('GREEN_ROOF', current))


if __name__ == '__main__':
    unittest.main()
