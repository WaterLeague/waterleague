"""고정 폭 배치의 경계·실제 강우 물수지·원 입력 보존 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from shapely.geometry import Polygon
from scripts.swale_geometry import contained_design
from waterleague_sim import shared_model
from waterleague_sim.engine import continuous, facilities, initialization
from waterleague_sim.historical_antecedent import load as load_antecedent
from waterleague_sim.historical_evaporation import load as load_evaporation
from waterleague_sim.model_catalog import read_catalog


def candidate():
    district = '2410520'
    cell = next(c for c in shared_model.candidates(district, 8).values() if 'VEGETATIVE_SWALE' in c['allowedTypes'])
    model, _, _ = shared_model.resolve({'district_id': district, 'cell_id': cell['id'],
        'model_hash': shared_model.site_catalog(8)[district]['sha256']})
    area = min(10, cell['physicalInputs']['swaleDesign']['maxAreaM2'])
    return model, {'cellId': cell['id'], 'facilityType': 'VEGETATIVE_SWALE', 'areaM2': area}


class SwaleTests(unittest.TestCase):
    def test_contained_design_rejects_missing_data_and_preserves_holes_and_notches(self):
        model, _ = candidate()
        cell = deepcopy(model['cells'][0])
        for coordinates in [[[0,0],[10,0],[10,5],[0,5],[0,0]],
                            [[0,0],[10,0],[10,2],[4,2],[4,8],[0,8],[0,0]]]:
            cell['coordinates'] = coordinates
            cell['maxAreaM2'] = Polygon(coordinates).area
            d = contained_design(cell)
            self.assertIsNotNone(d)
            self.assertTrue(Polygon(coordinates).covers(Polygon(d['coordinates'])))
            self.assertAlmostEqual(Polygon(d['coordinates']).area, d['maxAreaM2'])
            self.assertEqual(d['maxAreaM2'], 2*d['maxLengthM'])
        for change in [{'slopePercent': 0}, {'slopePercent': 3.001},
                       {'slopeMethod': 'UNRESOLVED_DESIGN_ASSUMPTION'}, {'soilStatus': 'UNKNOWN'}]:
            changed = deepcopy(cell);changed['physicalInputs'].update(change)
            self.assertIsNone(contained_design(changed))
        cell['coordinates'] = [[0,0],[10,0],[10,1],[0,1],[0,0]]
        self.assertIsNone(contained_design(cell))

    def test_catalog_and_every_candidate_preserve_old_geometry(self):
        count = 0
        for district in shared_model.site_catalog():
            current = shared_model.candidates(district, 8)
            previous = shared_model.candidates(district, 7)
            self.assertEqual(current.keys(), previous.keys())
            for key, cell in current.items():
                restored = deepcopy(cell)
                if 'VEGETATIVE_SWALE' in cell['allowedTypes']:
                    d = facilities.swale_design(cell)
                    self.assertTrue(Polygon(cell['coordinates']).covers(Polygon(d['coordinates'])))
                    self.assertEqual(d, contained_design(cell))
                    count += 1
                    restored['allowedTypes'].remove('VEGETATIVE_SWALE')
                    restored['physicalInputs'].pop('swaleDesign')
                self.assertEqual(restored, previous[key])
        self.assertEqual(count, 1021)
        for name, profile in facilities.catalog(2)['profiles'].items():
            self.assertEqual(profile, facilities.catalog(3)['profiles'][name])

    def test_swale_width_sides_and_area_cap(self):
        model, placement = candidate()
        model['rainfall'] = dict(start='2022-08-08T00:00:00+09:00', end='2022-08-08T00:01:00+09:00', intervalSeconds=60, depthsMm=[0])
        source = continuous.input_source(model, [placement], None)
        usage = source.split('[LID_USAGE]')[1].split('[')[0].strip().split()
        self.assertEqual(usage[1], 'VS');self.assertEqual(usage[4:7], ['2','0','0'])
        self.assertIn('VS SURFACE 250 0.1 0.15', source)
        self.assertTrue(next(line for line in source.splitlines() if line.startswith('VS SURFACE')).endswith('2.5'))
        for area in [model['cells'][0]['maxAreaM2'], float('nan'), -1]:
            with self.assertRaises(continuous.SimulationQualityError):
                continuous.input_source(model, [placement | {'areaM2': area}], None)

    @unittest.skipUnless(continuous.library_path().exists(), '연속 EPA 엔진 필요')
    def test_actual_observed_spinup_balance_and_exact_replay(self):
        model, placement = candidate()
        records = read_catalog(continuous.ROOT/'data/models')
        model_hash, observed = next((key, json.loads(raw)) for key, raw in records.items()
            if json.loads(raw).get('mapId') == 'seoul-osm-v1-2410520'
            and json.loads(raw).get('rainfall', {}).get('start', '').startswith('2022-08-08'))
        model['rainfall'] = observed['rainfall']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evaporation = load_evaporation(model_hash, observed, root/'sources')
            antecedent = load_antecedent(model_hash, root/'sources')
            expanded, pet = initialization.prepend(model, evaporation, antecedent)
            result = continuous.experiment(expanded, placement, root/'first', pet)
            replay = continuous.experiment(expanded, placement, root/'second', pet)
            final = result['strategy']['final']
            self.assertGreater(final['lidInfiltrationM3'], 0)
            self.assertGreater(final['lidSurfaceRunoffM3'], 0)
            self.assertEqual(final['lidDrainageTotalM3'], 0)
            self.assertTrue(result['initialization']['scoreExcludesWarmup'])
            self.assertAlmostEqual(final['lidInflowM3'], sum(model['rainfall']['depthsMm'])*placement['areaM2']/1000, places=6)
            self.assertLess(abs(final['balanceResidualM3']), .01*(final['precipitationM3']+final['initialStorageM3']))
            self.assertEqual(result['strategy'], replay['strategy'])
            self.assertEqual((root/'first/strategy.out').read_bytes(), (root/'second/strategy.out').read_bytes())
            self.assertEqual((root/'first/facility-designs.json').read_bytes(), facilities.CATALOG_V3_PATH.read_bytes())
            print(json.dumps({'station': model['rainfall']['stationId'], 'rainMm': sum(model['rainfall']['depthsMm']),
                'areaM2':placement['areaM2'], 'infiltrationM3': final['lidInfiltrationM3'],
                'surfaceRunoffM3':final['lidSurfaceRunoffM3'], 'balanceResidualM3': final['balanceResidualM3'],
                'exactReplay': True}), flush=True)


if __name__ == '__main__': unittest.main()
