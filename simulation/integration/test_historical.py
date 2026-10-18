"""전용 임시 DB에서 공개 확장 후보·실제 과거 강우·산출물 검증."""
import hashlib
import json
import unittest
import uuid
from datetime import datetime, timedelta
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

    def test_full_event_submission_two_districts_ignores_install_times_and_publishes_once(self):
        from waterleague_sim.run_historical_submission import POLICY
        _, sites, models = catalog()
        registry = json.loads((historical.ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        event = registry['events'][0]
        forcing = {m['districtId']: m['modelHash'] for m in event['models']}
        primary = forcing['2410520']
        rain = json.loads(models[primary])['rainfall']
        rules = {'policy': POLICY, 'eventId': event['id'], 'rainfallModels': forcing,
                 'engineVersion': '5.2.4', 'start': rain['start'], 'end': rain['end'],
                 'modelGrade': 'CURRENT_GEOMETRY_HISTORICAL_RAINFALL_STRESS_TEST'}
        rules_raw = json.dumps(rules, sort_keys=True)
        rules_hash = hashlib.sha256(rules_raw.encode()).hexdigest()
        totals, binaries = [], []
        for offset in (137, 3717):
            rows = []
            for district in ('2410520','2419953'):
                site = next(v for k,v in candidates(district).items() if k.startswith('RW') and v['maxAreaM2'] >= 20)
                rows.append({'districtId': district, 'cellId': site['id'], 'siteModelHash': sites[district]['sha256'],
                    'facilityType': 'GREEN_ROOF', 'areaM2': 20, 'rainfallModelHash': forcing[district],
                    'experimentInstalledAt': (datetime.fromisoformat(rain['start'])+timedelta(seconds=offset)).isoformat()})
            rows[0].update(submissionPolicy=POLICY,submissionRulesRaw=rules_raw,submissionRulesHash=rules_hash,
                           submissionRequestRaw=json.dumps({'testOnly':True,'placements':rows.copy()},sort_keys=True))
            body = json.dumps(rows, sort_keys=True)
            input_hash = hashlib.sha256((primary+'\n'+body).encode()).hexdigest()
            identity = uuid.uuid4()
            self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
                (identity,self.owner,uuid.uuid4(),'2410520',primary,input_hash,body))
            self.conn.execute('INSERT INTO historical_submissions(job_id,event_id,rules_hash,request_raw,cost) VALUES(%s,%s,%s,%s,14000000)',
                (identity,event['id'],rules_hash,rows[0]['submissionRequestRaw']))
            job = queue.claim(self.conn)
            self.assertTrue(historical.process(self.conn,job,self.artifacts))
            row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result = json.loads(row['result'])
            self.assertEqual(result['submissionPolicy'],POLICY)
            self.assertIsNone(result['officialTotalScore'])
            self.assertEqual(len(result['districts']),2)
            self.assertAlmostEqual(result['differenceM3'],sum(d['result']['differenceM3'] for d in result['districts']))
            for district in result['districts']:
                self.assertEqual(district['result']['start'],rain['start'])
                self.assertEqual(district['result']['end'],rain['end'])
                init = district['result']['facilities'][0]['initialization']
                self.assertEqual(init['warmupMinutes'],10080)
                self.assertEqual(datetime.fromisoformat(init['evaluationStart']),datetime.fromisoformat(rain['start']))
            posted = self.conn.execute('SELECT difference_m3 FROM historical_submissions WHERE job_id=%s',(identity,)).fetchone()['difference_m3']
            self.assertAlmostEqual(float(posted),result['differenceM3'])
            self.assertFalse(queue.finish(self.conn,job,'SUCCEEDED',{'stale':True},None))
            path=self.artifacts/'historical'/str(identity)/str(job['lease_token'])
            manifest=json.loads((path/'manifest.json').read_text())
            for name,digest in manifest.items(): self.assertEqual(hashlib.sha256((path/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(manifest['submission-rules.json'],rules_hash)
            totals.append(result['differenceM3'])
            binaries.append({k:v for k,v in manifest.items() if k.endswith(('.inp','.out'))})
        self.assertEqual(totals[0],totals[1])
        self.assertEqual(binaries[0],binaries[1])
        rows[1]['rainfallModelHash']='0'*64
        body=json.dumps(rows,sort_keys=True)
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),'2410520',primary,hashlib.sha256((primary+'\n'+body).encode()).hexdigest(),body))
        self.conn.execute('INSERT INTO historical_submissions(job_id,event_id,rules_hash,request_raw,cost) VALUES(%s,%s,%s,%s,14000000)',
            (identity,event['id'],rules_hash,rows[0]['submissionRequestRaw']))
        self.assertTrue(historical.process(self.conn,queue.claim(self.conn),self.artifacts))
        self.assertEqual(self.conn.execute('SELECT state FROM historical_experiments WHERE id=%s',(identity,)).fetchone()['state'],'FAILED')
        self.assertIsNone(self.conn.execute('SELECT difference_m3 FROM historical_submissions WHERE job_id=%s',(identity,)).fetchone()['difference_m3'])

    def test_timed_installations_real_weather_no_future_scores_and_replay(self):
        district = '2419953'
        _, sites, models = catalog()
        registry = json.loads((historical.ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        observed = json.loads(models[model_hash])
        start = datetime.fromisoformat(observed['rainfall']['start'])
        cells = [v for k,v in candidates(district).items() if k.startswith('RW') and v['maxAreaM2'] >= 1][:2]
        rows = [{'districtId': district, 'cellId': c['id'], 'siteModelHash': sites[district]['sha256'],
                 'facilityType': 'GREEN_ROOF', 'areaM2': 1, 'temporalPolicy': 'INSTALLATION_TIME_EXPERIMENT_V1',
                 'installedAt': (start+timedelta(seconds=offset)).isoformat()}
                for c,offset in zip(cells, (77, 197), strict=True)]
        placements = json.dumps(rows, sort_keys=True)
        input_hash = hashlib.sha256((model_hash+'\n'+placements).encode()).hexdigest()
        outputs = []
        for _ in range(2):
            identity = uuid.uuid4()
            self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
                (identity,self.owner,uuid.uuid4(),district,model_hash,input_hash,placements))
            job = queue.claim(self.conn)
            self.assertTrue(historical.process(self.conn,job,self.artifacts))
            row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            result = json.loads(row['result']); outputs.append(result)
            self.assertEqual(result['frames'][0]['differenceM3'], 0)
            self.assertEqual(result['frames'][0]['baselineAccountedM3'], 0)
            self.assertEqual(result['frames'][-1]['differenceM3'], result['differenceM3'])
            self.assertEqual(result['differenceM3'], sum(f['frames'][-1]['differenceM3'] for f in result['facilities']))
            for facility, expected in zip(result['facilities'], rows, strict=True):
                self.assertEqual(datetime.fromisoformat(facility['frames'][0]['at']), datetime.fromisoformat(expected['installedAt']))
                self.assertEqual(facility['frames'][0]['differenceM3'], 0)
                self.assertTrue(all(datetime.fromisoformat(f['at']) >= datetime.fromisoformat(expected['installedAt']) for f in facility['frames']))
                self.assertTrue(facility['initialization']['scoreExcludesWarmup'])
                self.assertGreater(facility['initialization']['preActivationSeconds'], 7*86400)
            path = self.artifacts/'historical'/str(identity)/str(job['lease_token'])
            manifest = json.loads((path/'manifest.json').read_text())
            self.assertIn('0/temporal.py', manifest)
            self.assertEqual(manifest['0/temporal.py'], hashlib.sha256((path/'0/temporal.py').read_bytes()).hexdigest())
        self.assertEqual(outputs[0], outputs[1])
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

    def test_bioretention_public_soil_candidate_through_worker_queue(self):
        district = '2410520'
        _, sites, _ = catalog()
        registry = json.loads((historical.ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cell = next(c for c in candidates(district).values() if 'BIORETENTION' in c['allowedTypes'])
        placements = json.dumps([{'districtId': district, 'cellId': cell['id'], 'siteModelHash': sites[district]['sha256'],
            'facilityType': 'BIORETENTION', 'areaM2': 20}], sort_keys=True)
        identity = uuid.uuid4()
        input_hash = hashlib.sha256((model_hash+'\n'+placements).encode()).hexdigest()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),district,model_hash,input_hash,placements))
        job = queue.claim(self.conn)
        self.assertTrue(historical.process(self.conn,job,self.artifacts))
        row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result = json.loads(row['result'])['facilities'][0]
        self.assertEqual(result['facilityDesign']['profile']['type'], 'BC')
        self.assertGreater(result['infiltrationM3'], 0)
        self.assertEqual(result['initialization']['warmupMinutes'], 10080)
        path = self.artifacts/'historical'/str(identity)/str(job['lease_token'])
        manifest = json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['0/facility-designs.json'], result['facilityDesign']['catalogSha256'])

    def test_swale_fixed_width_candidate_through_worker_queue(self):
        district = '2410520'
        _, sites, _ = catalog()
        registry = json.loads((historical.ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cell = next(c for c in candidates(district).values() if 'VEGETATIVE_SWALE' in c['allowedTypes'])
        placements = json.dumps([{'districtId': district, 'cellId': cell['id'], 'siteModelHash': sites[district]['sha256'],
            'facilityType': 'VEGETATIVE_SWALE', 'areaM2': cell['physicalInputs']['swaleDesign']['maxAreaM2'],
            'initializationSensitivity': 'SELECTED_SWALE_7_DAY_STATE_V2'}], sort_keys=True)
        identity = uuid.uuid4()
        input_hash = hashlib.sha256((model_hash+'\n'+placements).encode()).hexdigest()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),district,model_hash,input_hash,placements))
        job = queue.claim(self.conn)
        self.assertTrue(historical.process(self.conn,job,self.artifacts))
        row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result = json.loads(row['result'])['facilities'][0]
        self.assertEqual(result['facilityDesign']['profile']['type'], 'VS')
        state = json.loads(row['result'])['initializationSensitivity']
        self.assertEqual(state['seedPolicy'], 'NOT_APPLICABLE_FIXED_EMPTY_SURFACE')
        self.assertEqual([c['seedSaturationPercent'] for c in state['cases']], [0])
        self.assertEqual(state['comparison']['seedDifferences'], [])
        self.assertTrue(state['cases'][0]['initialization']['scoreExcludesWarmup'])
        self.assertAlmostEqual(state['cases'][0]['metrics']['contributionM3'], result['differenceM3'], places=8)
        self.assertGreater(result['infiltrationM3'], 0)
        self.assertEqual(result['initialization']['warmupMinutes'], 10080)
        path = self.artifacts/'historical'/str(identity)/str(job['lease_token'])
        manifest = json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['0/facility-designs.json'], result['facilityDesign']['catalogSha256'])


    def test_trench_fixed_width_candidate_through_worker_queue(self):
        district = '2410520'
        _, sites, _ = catalog()
        registry = json.loads((historical.ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cell = next(c for c in candidates(district).values() if 'INFILTRATION_TRENCH' in c['allowedTypes'])
        placements = json.dumps([{'districtId': district, 'cellId': cell['id'], 'siteModelHash': sites[district]['sha256'],
            'facilityType': 'INFILTRATION_TRENCH', 'areaM2': cell['physicalInputs']['trenchDesign']['maxAreaM2']}], sort_keys=True)
        identity = uuid.uuid4()
        input_hash = hashlib.sha256((model_hash+'\n'+placements).encode()).hexdigest()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),district,model_hash,input_hash,placements))
        job = queue.claim(self.conn)
        self.assertTrue(historical.process(self.conn,job,self.artifacts))
        row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result = json.loads(row['result'])['facilities'][0]
        self.assertEqual(result['facilityDesign']['profile']['type'], 'IT')
        self.assertGreater(result['infiltrationM3'], 0)
        self.assertEqual(result['initialization']['warmupMinutes'], 10080)
        path = self.artifacts/'historical'/str(identity)/str(job['lease_token'])
        manifest = json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['0/facility-designs.json'], result['facilityDesign']['catalogSha256'])
