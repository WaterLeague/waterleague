"""공개 후보·관측 입력에서 생물저류의 경계와 연속 수지 확인."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from waterleague_sim import shared_model
from waterleague_sim.engine import continuous, facilities, initialization
from waterleague_sim.historical_antecedent import load as load_antecedent
from waterleague_sim.historical_evaporation import load as load_evaporation
from waterleague_sim.model_catalog import read_catalog


def candidate():
    district = '2410520'
    snapshot = shared_model.candidate_snapshot(district, 7)
    cell = next(c for c in snapshot['cells'] if 'BIORETENTION' in c['allowedTypes'])
    model, _, _ = shared_model.resolve({'district_id': district, 'cell_id': cell['id'],
        'model_hash': shared_model.site_catalog(7)[district]['sha256']})
    return model, {'cellId': cell['id'], 'facilityType': 'BIORETENTION', 'areaM2': 20}


class BioretentionTests(unittest.TestCase):
    def test_ground_soil_binding_and_old_catalog_preservation(self):
        model, placement = candidate()
        old = facilities.catalog(1)
        for name, profile in old['profiles'].items():
            self.assertEqual(profile, facilities.catalog(2)['profiles'][name])
        self.assertEqual(model['unitCosts']['BIORETENTION'], 560000)
        self.assertEqual(model['sharedSiteSource']['inflowPolicy'], 'DIRECT_RAINFALL_ONLY')
        cell = model['cells'][0]
        self.assertEqual(facilities.bioretention_boundary(cell), cell['physicalInputs']['bioretentionBoundary'])
        for changed in [cell | {'kind': 'ROOF'}, cell | {'physicalInputs': {}},
                        cell | {'physicalInputs': cell['physicalInputs'] | {'conductivityMmH': 0}}]:
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'BIORETENTION_BOUNDARY'):
                facilities.bioretention_boundary(changed)
        self.assertNotIn('BIORETENTION', shared_model.candidate_snapshot('2410520', 6)['unitCosts'])

    @unittest.skipUnless(continuous.library_path().exists(), '연속 EPA 엔진 필요')
    def test_actual_observed_spinup_balance_and_replay(self):
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
            source = continuous.input_source(expanded, [placement], pet)
            self.assertIn('BC STORAGE 304.8 0.5384615384615384', source)
            self.assertNotIn('BC DRAIN ', source)
            forged = deepcopy(expanded)
            forged['cells'][0]['physicalInputs']['bioretentionBoundary']['seepageMmH'] *= 2
            with self.assertRaisesRegex(continuous.SimulationQualityError, 'BIORETENTION_BOUNDARY'):
                continuous.input_source(forged, [placement], pet)
            result = continuous.experiment(expanded, placement, root/'first', pet)
            replay = continuous.experiment(expanded, placement, root/'second', pet)
            final = result['strategy']['final']
            self.assertGreater(final['lidInfiltrationM3'], 0)
            self.assertEqual(final['lidDrainageTotalM3'], 0)
            self.assertTrue(result['initialization']['scoreExcludesWarmup'])
            self.assertGreater(result['strategy']['initial']['soilMoisture'], .08)
            self.assertAlmostEqual(final['lidInflowM3'], sum(model['rainfall']['depthsMm'])*placement['areaM2']/1000, places=6)
            self.assertLess(abs(final['balanceResidualM3']), .01*(final['precipitationM3']+final['initialStorageM3']))
            self.assertEqual(result['strategy'], replay['strategy'])
            self.assertEqual((root/'first/strategy.out').read_bytes(), (root/'second/strategy.out').read_bytes())
            self.assertEqual((root/'first/facility-designs.json').read_bytes(), facilities.CATALOG_V2_PATH.read_bytes())
            print(json.dumps({'station': model['rainfall']['stationId'], 'rainMm': sum(model['rainfall']['depthsMm']),
                'soilMoisture': result['strategy']['initial']['soilMoisture'], 'infiltrationM3': final['lidInfiltrationM3'],
                'balanceResidualM3': final['balanceResidualM3'], 'exactReplay': True}), flush=True)


if __name__ == '__main__':
    unittest.main()
