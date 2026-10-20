"""전용 임시 DB에서 공개 확장 후보·실제 과거 강우·산출물 검증."""
import hashlib
import gzip
from contextlib import closing
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import test_worker_queue as queue_fixture
from waterleague_sim import queue, historical
from waterleague_sim import admission
from waterleague_sim.spatial import game_catalog
from waterleague_sim.spatial.play_bundle import open_catalog
from waterleague_sim.forcing.archived_game_weather import read_source
from native_contract_evidence import verify as verify_contract

class HistoricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        queue_fixture.WorkerQueueTests.setUpClass.__func__(cls)
        cls.native = open_catalog()
        reference = game_catalog.catalog()['events']
        raw = game_catalog._read(reference['file'])
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise RuntimeError('현재 재해 목록 해시 불일치')
        cls.registry = json.loads(raw)
        source = json.loads((historical.ROOT / 'backend/src/main/resources/infrastructure/native-v1/associations.json').read_bytes())
        cls.asset_policy = {key: source[key] for key in
            ('version', 'sourceSha256', 'siteCatalogSha256', 'scope', 'historicalExistenceVerified')}
        cls.asset_policy.update(sha256=admission.NATIVE_SHA256, confirmedFootprintCount=0)

    def catalog(self):
        districts = game_catalog.regions()
        sites = {key: {'sha256': self.native.sha256} for key in districts}
        models = {row['sha256']: game_catalog.forcing(row['sha256']) for row in game_catalog.catalog()['models']}
        return districts, sites, models

    def candidates(self, district):
        # 원형 전체를 메모리에 복제하지 않고 고정 순서의 실제 후보만 시험한다.
        with closing(self.native.connection()) as db:
            rows = db.execute("SELECT body FROM sites WHERE district_id=? AND allowed_mask<>0 ORDER BY id LIMIT 512", (district,))
            return {cell['id']: cell for (body,) in rows if (cell := json.loads(body))}

    def encode(self, rows, *, sort_keys=True):
        for row in rows:
            row['publicAssetPolicy'] = self.asset_policy
        return json.dumps(rows, sort_keys=sort_keys)
    connection = queue_fixture.WorkerQueueTests.connection
    def setUp(self):
        queue_fixture.WorkerQueueTests.setUp(self)

    # 후속 인증 HTTP 검사가 마지막 작업의 DB와 산출물을 읽도록 끝에 실행한다.
    def test_z_server_frozen_pavement_comparison_and_ordinary_design_are_separate(self):
        fixture = os.environ.get('WL_PAVEMENT_FIXTURE')
        if not fixture:
            self.skipTest('서버 동결 요청 필요')
        destination = os.environ.get('WL_PAVEMENT_EVIDENCE')
        if destination:
            target = Path(destination)
            target.mkdir(mode=0o700)
            self.artifacts = target/'artifacts'
        request = json.loads(Path(fixture).read_text())
        self.assertEqual(request['inputHash'], hashlib.sha256(
            (request['modelHash']+'\n'+request['placements']).encode()).hexdigest())
        original_rows = json.loads(request['placements'])
        self.assertEqual(len(original_rows), 1)
        outcomes = []
        for comparison in (True, False):
            rows = json.loads(request['placements'])
            if not comparison:
                for row in rows:
                    row.pop('pavementMaintenanceComparison', None)
                    row.pop('pavementMaintenanceCatalogSha256', None)
            body = request['placements'] if comparison else json.dumps(rows, ensure_ascii=False)
            input_hash = hashlib.sha256((request['modelHash']+'\n'+body).encode()).hexdigest()
            identity = uuid.uuid4()
            self.conn.execute("""INSERT INTO historical_experiments
                (id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())""",
                (identity, self.owner, uuid.uuid4(), request['districtId'], request['modelHash'], input_hash, body))
            job = queue.claim(self.conn)
            self.assertTrue(historical.process(self.conn, job, self.artifacts))
            row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s', (identity,)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            result = json.loads(row['result'])
            path = self.artifacts/'historical'/str(identity)/str(job['lease_token'])
            outcomes.append((result, path))
            self.assertFalse(queue.finish(self.conn, job, 'SUCCEEDED', {'stale': True}, None))
        report = outcomes[0][0]['pavementMaintenanceComparison']
        self.assertEqual(report['status'], 'SUCCEEDED')
        self.assertFalse(report['rankingEligible'])
        self.assertEqual(report['cleaningRecovery']['value'], None)
        self.assertNotIn('pavementMaintenanceComparison', outcomes[1][0])
        for key in ('differenceM3', 'baselineAccountedM3', 'designAccountedM3', 'frames'):
            self.assertEqual(outcomes[0][0][key], outcomes[1][0][key])
        for name in ('baseline.inp', 'baseline.out', 'strategy.inp', 'strategy.out'):
            self.assertEqual((outcomes[0][1]/'0'/name).read_bytes(),
                             (outcomes[1][1]/'0'/name).read_bytes())
        manifest = json.loads((outcomes[0][1]/'manifest.json').read_text())
        self.assertEqual(manifest['pavement-comparison/input.json'], report['inputSha256'])
        self.assertTrue(all('pavement-comparison/'+case['scenario']['id']+'.out' in manifest
                            for case in report['cases']))
        if destination:
            (target/'comparison.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False)+'\n')
            (target/'request.json').write_bytes(Path(fixture).read_bytes())
            (target/'evidence.json').write_text(json.dumps({
                'classification': 'ACTUAL_SERVER_FROZEN_REQUEST_AND_WORKER_RESULT',
                'ordinaryDesignNativeFilesUnchanged': True, 'ordinaryMetricsUnchanged': True,
                'sourceManifest': manifest,
            }, ensure_ascii=False, allow_nan=False)+'\n')

    def test_full_event_submission_two_districts_ignores_install_times_and_publishes_once(self):
        from waterleague_sim.run_historical_submission import POLICY
        _, sites, models = self.catalog()
        registry = self.registry
        event = registry['events'][0]
        forcing = {m['districtId']: m['modelHash'] for m in event['models']}
        primary = forcing['11290']
        rain = json.loads(models[primary])['rainfall']
        rules = {'policy': POLICY, 'eventId': event['id'], 'rainfallModels': forcing,
                 'engineVersion': '5.2.4', 'start': rain['start'], 'end': rain['end'],
                 'modelGrade': 'CURRENT_GEOMETRY_HISTORICAL_RAINFALL_STRESS_TEST'}
        from waterleague_sim.evaluation import score_policy
        policy_raw, policy = score_policy.verified_policy()
        rules['scorePolicy'] = {k: v for k, v in policy.items() if k != 'files'} | {'sha256': score_policy.digest(policy_raw)}
        rules_raw = json.dumps(rules, sort_keys=True)
        rules_hash = hashlib.sha256(rules_raw.encode()).hexdigest()
        totals, binaries = [], []
        for offset in (137, 3717):
            rows = []
            for district in ('11290','11200'):
                site = next(v for k,v in self.candidates(district).items() if 'GREEN_ROOF' in v['allowedTypes'] and v['maxAreaM2'] >= 20)
                rows.append({'districtId': district, 'cellId': site['id'], 'siteModelHash': sites[district]['sha256'],
                    'facilityType': 'GREEN_ROOF', 'areaM2': 20, 'rainfallModelHash': forcing[district],
                    'experimentInstalledAt': (datetime.fromisoformat(rain['start'])+timedelta(seconds=offset)).isoformat()})
            rows[0].update(submissionPolicy=POLICY,submissionRulesRaw=rules_raw,submissionRulesHash=rules_hash,
                           submissionRequestRaw=json.dumps({'testOnly':True,'placements':rows.copy()},sort_keys=True))
            body = self.encode(rows, sort_keys=True)
            input_hash = hashlib.sha256((primary+'\n'+body).encode()).hexdigest()
            identity = uuid.uuid4()
            self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
                (identity,self.owner,uuid.uuid4(),'11290',primary,input_hash,body))
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
            verify_contract(self, path)
            manifest=json.loads((path/'manifest.json').read_text())
            for name,digest in manifest.items(): self.assertEqual(hashlib.sha256((path/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(manifest['submission-rules.json'],rules_hash)
            totals.append(result['differenceM3'])
            binaries.append({k:v for k,v in manifest.items() if k.endswith(('.inp','.out'))})
        self.assertEqual(totals[0],totals[1])
        self.assertEqual(binaries[0],binaries[1])
        rows[1]['rainfallModelHash']='0'*64
        body=self.encode(rows,sort_keys=True)
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),'11290',primary,hashlib.sha256((primary+'\n'+body).encode()).hexdigest(),body))
        self.conn.execute('INSERT INTO historical_submissions(job_id,event_id,rules_hash,request_raw,cost) VALUES(%s,%s,%s,%s,14000000)',
            (identity,event['id'],rules_hash,rows[0]['submissionRequestRaw']))
        self.assertTrue(historical.process(self.conn,queue.claim(self.conn),self.artifacts))
        self.assertEqual(self.conn.execute('SELECT state FROM historical_experiments WHERE id=%s',(identity,)).fetchone()['state'],'FAILED')
        self.assertIsNone(self.conn.execute('SELECT difference_m3 FROM historical_submissions WHERE job_id=%s',(identity,)).fetchone()['difference_m3'])

    def test_timed_installations_real_weather_no_future_scores_and_replay(self):
        district = '11200'
        _, sites, models = self.catalog()
        registry = self.registry
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        observed = json.loads(models[model_hash])
        start = datetime.fromisoformat(observed['rainfall']['start'])
        cells = [v for k,v in self.candidates(district).items() if 'GREEN_ROOF' in v['allowedTypes'] and v['maxAreaM2'] >= 1][:2]
        rows = [{'districtId': district, 'cellId': c['id'], 'siteModelHash': sites[district]['sha256'],
                 'facilityType': 'GREEN_ROOF', 'areaM2': 1, 'temporalPolicy': 'INSTALLATION_TIME_EXPERIMENT_V1',
                 'installedAt': (start+timedelta(seconds=offset)).isoformat()}
                for c,offset in zip(cells, (77, 197), strict=True)]
        placements = self.encode(rows, sort_keys=True)
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
            verify_contract(self, path)
            manifest = json.loads((path/'manifest.json').read_text())
            self.assertIn('0/temporal.py', manifest)
            self.assertEqual(manifest['0/temporal.py'], hashlib.sha256((path/'0/temporal.py').read_bytes()).hexdigest())
        self.assertEqual(outputs[0], outputs[1])
    def test_expanded_candidates_real_rainfall_and_preserved_hashes(self):
        district='11200'
        districts, sites, models = self.catalog()
        registry=self.registry
        model_hash=next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cells = self.candidates(district)
        cell_id = next(k for k,v in cells.items() if 'GREEN_ROOF' in v['allowedTypes'] and v['maxAreaM2'] >= 1)
        budget_policy = json.loads((historical.ROOT/'backend/src/main/resources/budget/seoul-2026.json').read_text())
        placements = self.encode([{'districtId':district,'cellId':cell_id,'siteModelHash':sites[district]['sha256'],'facilityType':'GREEN_ROOF','areaM2':1,'budgetPolicy':budget_policy,
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
        _, prior = game_catalog.climate_binding('antecedent', model_hash)
        reference = prior['rainfall']
        raw = read_source('data/derived/antecedent/' + reference['file'], reference['sha256'])
        self.assertAlmostEqual(initialization['warmupRainMm'], sum(json.loads(gzip.decompress(raw))['depthsMm']))
        self.assertGreater(initialization['initialSoilMoisture'],.125)
        self.assertEqual(result['facilities'][0]['facilityDesign']['profile']['id'],'EPA_GR_150_V1')
        path=self.artifacts/'historical'/str(identity)/str(job['lease_token'])
        verify_contract(self, path)
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
        district = '11290'
        _, sites, _ = self.catalog()
        registry = self.registry
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cell = next(c for c in self.candidates(district).values() if 'BIORETENTION' in c['allowedTypes'])
        placements = self.encode([{'districtId': district, 'cellId': cell['id'], 'siteModelHash': sites[district]['sha256'],
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
        verify_contract(self, path)
        manifest = json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['0/facility-designs.json'], result['facilityDesign']['catalogSha256'])

    def test_swale_fixed_width_candidate_through_worker_queue(self):
        district = '11290'
        _, sites, _ = self.catalog()
        registry = self.registry
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cell = next(c for c in self.candidates(district).values() if 'VEGETATIVE_SWALE' in c['allowedTypes'])
        placements = self.encode([{'districtId': district, 'cellId': cell['id'], 'siteModelHash': sites[district]['sha256'],
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
        verify_contract(self, path)
        manifest = json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['0/facility-designs.json'], result['facilityDesign']['catalogSha256'])


    def test_trench_fixed_width_candidate_through_worker_queue(self):
        district = '11290'
        _, sites, _ = self.catalog()
        registry = self.registry
        model_hash = next(m['modelHash'] for m in registry['events'][0]['models'] if m['districtId']==district)
        cell = next(c for c in self.candidates(district).values() if 'INFILTRATION_TRENCH' in c['allowedTypes'])
        placements = self.encode([{'districtId': district, 'cellId': cell['id'], 'siteModelHash': sites[district]['sha256'],
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
        verify_contract(self, path)
        manifest = json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['0/facility-designs.json'], result['facilityDesign']['catalogSha256'])
