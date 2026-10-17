"""관측소 선택·실제 강우 연결·기존 버전 보존과 SWMM 실행 확인."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pyproj
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.engine.swmm import experiment, library_path
from waterleague_sim.ingestion.kma import normalize

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT/path).read_text())


def digest(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


class RegionalRainfallTests(unittest.TestCase):
    def test_observation_selection_and_version_provenance(self):
        report = read('data/manifests/seoul-regional-rainfall-v1.json')
        self.assertEqual(report['collectorSha256'], digest('scripts/fetch_seoul_regional_rainfall.py'))
        self.assertEqual(len(report['selections']), 75)
        self.assertEqual(len({(s['mapId'], s['startKst']) for s in report['selections']}), 75)
        models = {h: json.loads(raw) for h, raw in read_catalog(ROOT/'data/models').items()}
        before = read('data/manifests/seoul-play-v1.json')
        after = read('data/manifests/seoul-play-v2.json')
        self.assertEqual(after, read('frontend/public/data/seoul-play-v2.json'))
        self.assertEqual(report['geometryRegistrySha256'], digest('data/manifests/seoul-play-v1.json'))
        self.assertEqual(after['rainfallSelectionManifestSha256'], digest('data/manifests/seoul-regional-rainfall-v1.json'))
        geod = pyproj.Geod(ellps='WGS84')
        for old, current in zip(before['regions'], after['regions'], strict=True):
            self.assertEqual(old['mapSha256'], current['mapSha256'])
            self.assertTrue(set(old['modelHashes']).issubset(current['modelHashes']))
            selections = [s for s in report['selections'] if s['mapId'] == old['mapId']]
            accepted = [s for s in selections if s['status'] == 'ACCEPTED']
            self.assertEqual(len(current['modelHashes']), 3+len(accepted))
            for s in selections:
                self.assertLessEqual(s['stationDistanceKm'], 10)
                if s['status'] != 'ACCEPTED':
                    self.assertTrue(s['reason'])
                    continue
                rain = read('data/derived/rainfall/'+s['rainfallId']+'.json')
                self.assertEqual(s['rainfallSha256'], digest('data/derived/rainfall/'+s['rainfallId']+'.json'))
                matching = [models[h] for h in current['modelHashes'] if models[h]['rainfall']['id'] == rain['id']]
                self.assertEqual(len(matching), 1)
                m = matching[0]
                self.assertEqual(m['cells'], models[old['defaultModelHash']]['cells'])
                self.assertEqual(m['regionalRainfallUse'], 'NEAREST_AWS_OBSERVED_REPLAY')
                self.assertEqual(m['rainfallModelGeneratorSha256'], digest('scripts/prepare_seoul_regional_rainfall_models.py'))
                station = rain['stationMetadata']
                center = read('frontend/public/data/'+old['mapFile'])['origin']
                distance = geod.inv(*center, station['longitude'], station['latitude'])[2]/1000
                self.assertAlmostEqual(s['stationDistanceKm'], distance, places=3)
                self.assertEqual(station['historicalValidity'], 'API_TIME_QUERY_CONFIRMED')
                for field, hash_field in [('sourceManifest', 'sourceSha256'), ('endSourceManifest', 'endSourceSha256')]:
                    self.assertEqual(station[hash_field], read('data/manifests/'+station[field])['sha256'])
                # 로컬 원본이 있을 때만 CI에 배포하지 않는 API 응답도 역검사한다.
                raw_stations = ROOT/'data/raw'/station['sourceManifest'].replace('.json', '.txt')
                if raw_stations.exists():
                    rows = [l.split() for l in raw_stations.read_bytes().decode('euc-kr').splitlines() if l and not l.startswith('#')]
                    nearest = min((geod.inv(*center, float(r[1]), float(r[2]))[2]/1000, r[0]) for r in rows)
                    self.assertEqual(nearest[1], s['stationId'])
                    end_stations = ROOT/'data/raw'/station['endSourceManifest'].replace('.json', '.txt')
                    last = next(l.split() for l in end_stations.read_bytes().decode('euc-kr').splitlines() if l.split() and l.split()[0] == s['stationId'])
                    self.assertEqual([float(last[i]) for i in (1, 2, 4)], [station[k] for k in ('longitude', 'latitude', 'elevationM')])
                raw = ROOT/'data/raw'/rain['sourceManifest'].replace('.json', '.txt')
                if raw.exists():
                    self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), rain['sourceHash'])
                    rows, total = normalize(raw.read_text())
                    self.assertEqual([float(r.depth_mm) for r in rows], rain['depthsMm'])
                    self.assertEqual(float(total), rain['totalDepthMm'])
            if accepted:
                latest = max(accepted, key=lambda s: s['startKst'])
                self.assertEqual(models[current['defaultModelHash']]['rainfall']['id'], latest['rainfallId'])
            else:
                self.assertEqual(current['defaultModelHash'], old['defaultModelHash'])

    @unittest.skipUnless(library_path().exists(), 'EPA 엔진 빌드 필요')
    def test_actual_swmm_three_observed_windows(self):
        models = [json.loads(raw) for raw in read_catalog(ROOT/'data/models').values()]
        new = [m for m in models if m.get('regionalRainfallUse') == 'NEAREST_AWS_OBSERVED_REPLAY']
        for day in ('20240622', '20240702', '20240718'):
            model = max((m for m in new if m['id'].endswith(day)), key=lambda m: m['rainfall']['windowStatistics']['peak60MinuteMm'])
            with self.subTest(model=model['id']), tempfile.TemporaryDirectory() as tmp:
                result = experiment(model, [{'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20}], Path(tmp))
                self.assertFalse(result['official'])
                for side in ('baseline', 'strategy'):
                    self.assertLess(abs(result[side]['runoffContinuityPercent']), 1)
                    self.assertEqual(len(result[side]['seriesM3s']), len(model['rainfall']['depthsMm']))
