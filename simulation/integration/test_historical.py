"""전용 임시 DB에서 공개 확장 후보·실제 과거 강우·산출물 검증."""
import hashlib
import json
import unittest
import uuid
from pathlib import Path
import test_worker_queue as queue_fixture
from waterleague_sim import queue, historical
from waterleague_sim.shared_model import catalog, candidates

class HistoricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        queue_fixture.WorkerQueueTests.setUpClass.__func__(cls)
    connection = queue_fixture.WorkerQueueTests.connection
    def setUp(self):
        queue_fixture.WorkerQueueTests.setUp(self)
    def test_expanded_candidates_real_rainfall_and_preserved_hashes(self):
        district='2419953'
        districts, sites, models = catalog()
        registry=json.loads((historical.ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        model_hash=next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cells = candidates(district)
        cell_id = next(k for k,v in cells.items() if k.startswith('RW') and v['maxAreaM2'] >= 1)
        budget_policy = json.loads((historical.ROOT/'backend/src/main/resources/budget/seoul-2026.json').read_text())
        placements = json.dumps([{'districtId':district,'cellId':cell_id,'siteModelHash':sites[district]['sha256'],'facilityType':'GREEN_ROOF','areaM2':1,'budgetPolicy':budget_policy,
                                  'initializationSensitivity':'SELECTED_SURFACE_7_DAY_DRY_WET_V1'}],sort_keys=True)
        input_hash = hashlib.sha256((model_hash+'\n'+placements).encode()).hexdigest()
        identity = uuid.uuid4()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",(identity,self.owner,uuid.uuid4(),district,model_hash,input_hash,placements))
        job = queue.claim(self.conn)
        self.assertEqual(job['queue_kind'],'HISTORICAL')
        self.assertTrue(historical.process(self.conn,job,self.artifacts))
        row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result = json.loads(row['result'])
        self.assertGreater(result['facilities'][0]['precipitationM3'],0)
        self.assertEqual(result['evaporationMethod'],'FAO56_HOURLY_LAGGED_ASOS_AWS_V1')
        self.assertGreater(result['facilities'][0]['evaporationM3'],0)
        self.assertEqual(len(result['frames']),len(json.loads(models[model_hash])['rainfall']['depthsMm']))
        self.assertEqual(result['facilities'][0]['cellId'],cell_id)
        self.assertEqual(result['facilities'][0]['budgetPolicy'],budget_policy)
        initialization=result['facilities'][0]['initialization']
        self.assertEqual(initialization['warmupMinutes'],10080)
        self.assertTrue(initialization['scoreExcludesWarmup'])
        self.assertAlmostEqual(initialization['warmupRainMm'],146)
        self.assertGreater(initialization['initialSoilMoisture'],.125)
        self.assertEqual(result['facilities'][0]['facilityDesign']['profile']['id'],'EPA_GR_150_V1')
        path=self.artifacts/'historical'/str(identity)/str(job['lease_token'])
        manifest=json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['rainfall-model.json'],model_hash)
        for file, digest in manifest.items(): self.assertEqual(hashlib.sha256((path/file).read_bytes()).hexdigest(),digest)
        comparison=result['initializationSensitivity']
        self.assertEqual(comparison,json.loads((path/'sensitivity/sensitivity.json').read_text()))
        self.assertEqual(comparison['cellId'],cell_id)
        self.assertEqual(comparison['comparison']['status'],'MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD')
        self.assertEqual([c['seedSaturationPercent'] for c in comparison['cases']],[0,100])
        self.assertTrue(all(c['status']=='SUCCEEDED' and c['days']==7 for c in comparison['cases']))
        self.assertAlmostEqual(comparison['cases'][0]['metrics']['contributionM3'],result['differenceM3'],places=8)
        self.assertEqual(comparison['cases'][0]['initialization']['warmupRainMm'],initialization['warmupRainMm'])
        self.assertEqual(manifest['sensitivity/input.json'],comparison['inputSha256'])
        self.assertTrue(all(f'sensitivity/design_7d_{seed}.inp' in manifest for seed in (0,100)))
        self.assertFalse(queue.finish(self.conn,job,'SUCCEEDED',{'stale':True},None))
