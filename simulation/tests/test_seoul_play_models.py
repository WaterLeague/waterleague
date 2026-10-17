"""구별 모델의 공간·강우 연결과 실제 엔진 실행 검사."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pyproj
from shapely.geometry import Polygon, MultiPolygon
from waterleague_sim.engine.swmm import experiment, library_path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT/path).read_text())


def geometry(feature):
    return MultiPolygon([Polygon(p[0], p[1:]) for p in feature['polygons']])


class SeoulPlayModelTests(unittest.TestCase):
    def test_all_districts_geometry_rainfall_and_versions(self):
        registry = read('data/manifests/seoul-play-v1.json')
        self.assertEqual(registry, read('frontend/public/data/seoul-play-v1.json'))
        city = read('frontend/public/data/seoul-v1/city.json')
        self.assertEqual({r['districtId'] for r in registry['regions']}, {d['id'] for d in city['districts']})
        generator = hashlib.sha256((ROOT/'scripts/prepare_seoul_play_models.py').read_bytes()).hexdigest()
        self.assertEqual(registry['generatorSha256'], generator)
        catalog = read('data/models/catalog.json')
        by_hash = {e['sha256']: e for e in catalog['models']}
        geod = pyproj.Geod(ellps='WGS84')
        for region in registry['regions']:
            raw = (ROOT/'frontend/public/data'/region['mapFile']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), region['mapSha256'])
            snapshot = json.loads(raw)
            features = {f['id']: f for f in snapshot['features']}
            parking = geometry(features[region['parkingSourceId']])
            buildings = [geometry(f) for f in features.values() if f['kind'] == 'building']
            self.assertEqual(len(region['modelHashes']), 3)
            first_cells = None
            for model_hash in region['modelHashes']:
                entry = by_hash[model_hash]
                raw = (ROOT/'data/models'/entry['file']).read_bytes()
                self.assertEqual(raw, (ROOT/'backend/src/main/resources/models'/entry['file']).read_bytes())
                self.assertEqual(hashlib.sha256(raw).hexdigest(), model_hash)
                model = json.loads(raw)
                self.assertEqual(model['geometryModelGeneratorSha256'], generator)
                self.assertEqual(model['mapSnapshotHash'], region['mapSha256'])
                self.assertEqual(model['mapId'], region['mapId'])
                self.assertEqual(model['regionalRainfallUse'], 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION')
                self.assertFalse(model['officialEvaluationAvailable'])
                rain = model['rainfall']; station = rain['stationMetadata']
                distance = geod.inv(station['longitude'], station['latitude'], *snapshot['origin'])[2]/1000
                self.assertAlmostEqual(rain['stationDistanceKm'], distance, places=3)
                original = read('data/derived/rainfall/'+rain['id']+'.json')
                for key in original:
                    if key not in ('stationDistanceKm', 'stationDistanceEvidence'):
                        self.assertEqual(rain[key], original[key])
                self.assertEqual(len(model['cells']), 13)
                if first_cells is not None:
                    self.assertEqual(model['cells'], first_cells)
                    continue
                first_cells = model['cells']
                shapes = []
                for cell in first_cells:
                    g = Polygon(cell['coordinates'])
                    self.assertTrue(g.is_valid)
                    self.assertAlmostEqual(g.area, cell['areaM2'], places=5)
                    self.assertTrue(all(g.intersection(other).area < .001 for other in shapes))
                    shapes.append(g)
                    self.assertEqual(cell['siteEligibility'], 'UNKNOWN')
                    if cell['kind'] == 'ROOF':
                        self.assertTrue(g.equals(geometry(features[cell['buildingId']])))
                    else:
                        self.assertEqual(cell['areaM2'], 25)
                        self.assertEqual(cell['maxAreaM2'], 20)
                        self.assertTrue(parking.covers(g))
                        self.assertTrue(all(not g.intersects(b) for b in buildings))

    @unittest.skipUnless(library_path().exists(), 'EPA 엔진 빌드 필요')
    def test_actual_swmm_all_districts(self):
        catalog = {e['sha256']: e for e in read('data/models/catalog.json')['models']}
        for i, region in enumerate(read('data/manifests/seoul-play-v1.json')['regions']):
            entry = catalog[region['modelHashes'][i % 3]]
            model = read('data/models/'+entry['file'])
            placements = [{'cellId': 'R1', 'facilityType': 'GREEN_ROOF', 'areaM2': 30},
                          {'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20},
                          {'cellId': 'G2', 'facilityType': 'PERMEABLE_PAVEMENT', 'areaM2': 20}]
            with self.subTest(district=region['districtName']), tempfile.TemporaryDirectory() as tmp:
                result = experiment(model, placements, Path(tmp))
                self.assertFalse(result['official'])
                for name in ('baseline', 'strategy'):
                    self.assertLess(abs(result[name]['runoffContinuityPercent']), 1)
