"""격리 DB의 회원 관망 요청·실제 공개 입력 계산·임대 보존 검증."""
import hashlib
import json
import os
from pathlib import Path
import unittest
import uuid
import test_worker_queue as fixture
from waterleague_sim import queue, watershed
from waterleague_sim.run_watershed_job import CATALOG, CATALOG_HASH, inputs
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.costing.watershed import CATALOG as COST_CATALOG, CATALOG_HASH as COST_HASH, snapshot
from flow_graph_evidence import verify as verify_graph


class WatershedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.WorkerQueueTests.setUpClass.__func__(cls)
        cls.requests = Path(os.environ['WL_WATERSHED_FIXTURES']).resolve(strict=True)
    connection=fixture.WorkerQueueTests.connection
    def setUp(self):
        fixture.WorkerQueueTests.setUp(self)

    def test_public_network_design_job_and_bound_artifacts(self):
        catalog=json.loads(CATALOG.read_text())
        design={'schemaVersion':1,'basis':catalog['designBasis'],'placements':[
            {'id':'Bio1','facilityType':'BIORETENTION','subcatchmentId':'S1','areaM2':100,
             'replacedImperviousM2':100,'treatedImperviousM2':1000,'initialSaturationPercent':0,
             'parameters':catalog['templates']['BIORETENTION']['parameters']}]}
        design['costing'] = snapshot(design['placements'], json.loads(COST_CATALOG.read_text()))
        raw=json.dumps(design,sort_keys=True)
        digest=hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest()
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",(identity,self.owner,uuid.uuid4(),CATALOG_HASH,digest,raw))
        job=queue.claim(self.conn)
        self.assertEqual(job['queue_kind'],'WATERSHED')
        self.assertTrue(watershed.process(self.conn,job,self.artifacts))
        row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result=json.loads(row['result'])
        self.assertEqual(result['numericalStatus'],'PASSED')
        for case in result['cases']:
            nodes=case['nodeFlooding']
            self.assertEqual(len(nodes['nodes']),28)
            self.assertTrue(all(n['mapped'] for n in nodes['nodes']))
            self.assertEqual(nodes['totalFloodingM3'],case['totals']['floodingM3'])
            self.assertAlmostEqual(sum(n['floodingM3'] for n in nodes['nodes']),nodes['totalFloodingM3'],places=5)
        self.assertFalse(result['rankingEligible'])
        self.assertIsNone(result['completeInstalledCostKrw'])
        self.assertEqual(result['costing'], design['costing'])
        self.assertEqual(result['costing']['knownReferenceSubtotalKrw'], 56000000)
        self.assertIsNone(result['costing']['budgetChargedKrw'])
        self.assertLess(result['signedReductionM3']['outflowM3'],0)
        self.assertGreater(result['signedReductionM3']['floodingM3'],0)
        directory=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        verify_graph(self, directory, result)
        import shutil
        from waterleague_sim.engine.swmm import ROOT
        evidence = ROOT/'tmp'/('flow-graph-network-'+str(identity))
        shutil.copytree(directory, evidence)
        (ROOT/'tmp/flow-graph-network-last-artifacts.txt').write_text(str(evidence))
        manifest=json.loads((directory/'manifest.json').read_text())
        for name,sha in manifest.items():
            self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),sha)
            if name!='result.json': self.assertEqual(result['artifactFiles'][name],sha)
        self.assertEqual(manifest['catalog.json'],CATALOG_HASH)
        self.assertEqual(manifest['network-layout.json'],result['networkLayout']['sha256'])
        self.assertEqual(manifest['cost-catalog.json'], COST_HASH)
        self.assertEqual(json.loads((directory/'cost-snapshot.json').read_text()), design['costing'])
        self.assertIn('strategy/network.out',manifest)
        self.assertFalse(queue.finish(self.conn,job,'SUCCEEDED',{'stale':True},None))
        request={'modelHash':CATALOG_HASH,'inputHash':digest,'placements':raw}
        with self.assertRaises(FloodModelError): inputs(request | {'inputHash':'0'*64})
        design['placements'][0]['parameters']['nativeSeepageMmH']=1000
        changed=json.dumps(design,sort_keys=True)
        with self.assertRaises(FloodModelError): inputs(request | {'placements':changed,'inputHash':hashlib.sha256((CATALOG_HASH+'\n'+changed).encode()).hexdigest()})

    def test_storage_only_and_combined_native_water_balance(self):
        from waterleague_sim.watershed_storage import CATALOG_HASH as STORAGE_HASH
        from waterleague_sim.reference.connected_storage import design as tank_design
        catalog=json.loads(CATALOG.read_text())
        lids=[{'id':'Bio1','facilityType':'BIORETENTION','subcatchmentId':'S1','areaM2':100,
            'replacedImperviousM2':100,'treatedImperviousM2':1000,'initialSaturationPercent':0,
            'parameters':catalog['templates']['BIORETENTION']['parameters']}]
        for mixed in (False, True):
            design={'schemaVersion':1,'basis':catalog['designBasis'],'placements':lids if mixed else []}
            base_request=design | {'placements':lids}
            raw=json.dumps(base_request,sort_keys=True)
            _,_,base,*_=inputs({'modelHash':CATALOG_HASH,'placements':raw,'inputHash':hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest()})
            design['storage']=tank_design(base,inlet='J1',receiver='J2',invert=16,depth=5,area=100,inlet_crest=18.5,drain_crest=16.2,overflow_crest=18.5) | {'catalogHash':STORAGE_HASH}
            raw=json.dumps(design,sort_keys=True)
            digest=hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest()
            identity=uuid.uuid4()
            self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",(identity,self.owner,uuid.uuid4(),CATALOG_HASH,digest,raw))
            job=queue.claim(self.conn)
            self.assertTrue(watershed.process(self.conn,job,self.artifacts))
            row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result=json.loads(row['result'])
            self.assertEqual(result['numericalStatus'],'PASSED',result)
            strategy=result['cases'][1]
            unmapped=[n for n in strategy['nodeFlooding']['nodes'] if not n['mapped']]
            self.assertEqual(len(unmapped),1)
            self.assertEqual(unmapped[0]['kind'],'STORAGE')
            ledger=strategy['connectedStorage']['wholeRunLedger']['facilities'][0]
            self.assertEqual(ledger['capacityM3'],500)
            self.assertGreater(ledger['inflowM3'],0)
            self.assertGreater(ledger['finalStorageM3'],0)
            self.assertEqual(ledger['floodingM3'],0)
            self.assertEqual(ledger['numericalStatus'],'PASSED')
            self.assertEqual(len(strategy['facilities']),int(mixed))
            self.assertFalse(result['rankingEligible'])
            self.assertIsNone(result['budgetChargedKrw'])
            directory=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
            manifest=json.loads((directory/'manifest.json').read_text())
            self.assertEqual(manifest['storage-connections.json'],STORAGE_HASH)
            self.assertEqual((directory/'baseline-input.inp').read_bytes(),base)
            self.assertIn(b'WLST_Tank', (directory/'strategy-input.inp').read_bytes())
            changed=json.loads(raw);changed['storage']['placements'][0]['drain']['nodeId']='Out1'
            invalid=json.dumps(changed,sort_keys=True)
            with self.assertRaises(FloodModelError): inputs({'modelHash':CATALOG_HASH,'placements':invalid,'inputHash':hashlib.sha256((CATALOG_HASH+'\n'+invalid).encode()).hexdigest()})

    def test_conduit_storage_and_lid_share_one_native_run(self):
        from waterleague_sim.watershed_conduits import CATALOG as PIPES,CATALOG_HASH as PIPE_HASH
        from waterleague_sim.watershed_storage import CATALOG_HASH as STORAGE_HASH
        from waterleague_sim.reference.connected_storage import design as tank_design
        catalog=json.loads(CATALOG.read_text());pipe_catalog=json.loads(PIPES.read_text())
        design={'schemaVersion':1,'basis':catalog['designBasis'],'placements':[
            {'id':'Bio1','facilityType':'BIORETENTION','subcatchmentId':'S1','areaM2':100,
             'replacedImperviousM2':100,'treatedImperviousM2':1000,'initialSaturationPercent':0,
             'parameters':catalog['templates']['BIORETENTION']['parameters']}]}
        def packed(d):
            raw=json.dumps(d,sort_keys=True)
            return raw,hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest()
        raw,digest=packed(design)
        base=inputs({'modelHash':CATALOG_HASH,'placements':raw,'inputHash':digest})[2]
        design['storage']=tank_design(base,inlet='J1',receiver='J2',invert=16,depth=5,area=100,inlet_crest=18.5,drain_crest=16.2,overflow_crest=18.5)|{'catalogHash':STORAGE_HASH}
        original=next(p['original'] for p in pipe_catalog['conduits'] if p['id']=='C2')
        design['conduits']={'schemaVersion':1,'catalogHash':PIPE_HASH,'sourceNetworkSha256':pipe_catalog['baseNetworkSha256'],
            'placements':[{'id':'Pipe1','conduitId':'C2',**original,'widthM':3,'basis':'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
                'evidence':'명시적 회원 관로 개량 설계; 현장 관측 제원 아님','original':original}]}
        raw,digest=packed(design);identity=uuid.uuid4()
        self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",(identity,self.owner,uuid.uuid4(),CATALOG_HASH,digest,raw))
        job=queue.claim(self.conn);self.assertTrue(watershed.process(self.conn,job,self.artifacts))
        row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code']);result=json.loads(row['result'])
        self.assertEqual(result['numericalStatus'],'PASSED',result)
        self.assertEqual(result['cases'][1]['connectedStorage']['numericalStatus'],'PASSED')
        for case in result['cases']:
            self.assertEqual(case['conduits'][0]['conduitId'],'C2')
            self.assertGreater(case['conduitStateTimeSeconds'],0)
        self.assertNotEqual(result['cases'][0]['totals'],result['cases'][1]['totals'])
        self.assertIsNone(result['completeInstalledCostKrw']);self.assertFalse(result['rankingEligible'])
        folder=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        verify_graph(self, folder, result)
        manifest=json.loads((folder/'manifest.json').read_text())
        self.assertEqual(manifest['conduit-catalog.json'],PIPE_HASH)
        self.assertEqual((folder/'baseline-input.inp').read_bytes(),base)

    def test_cistern_reference_quotes_are_bound_without_budget_or_physics_changes(self):
        from pathlib import Path
        from waterleague_sim.costing.cistern import CATALOG_SHA256
        from waterleague_sim.costing.cistern_reference import snapshot
        request=json.loads((self.requests/'cistern-server-request.json').read_bytes())
        raw=request['placements'];design=json.loads(raw);digest=request['inputHash']
        self.assertEqual(request['modelHash'],CATALOG_HASH)
        self.assertEqual(hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest(),digest)
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",(identity,self.owner,uuid.uuid4(),CATALOG_HASH,digest,raw))
        job=queue.claim(self.conn)
        self.assertTrue(watershed.process(self.conn,job,self.artifacts))
        row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result=json.loads(row['result'])
        self.assertEqual(result['numericalStatus'],'PASSED')
        self.assertEqual(result['cisternCosting'],snapshot(design['placements']))
        finance = result['cisternLifeCycleCosts']
        self.assertEqual(finance['catalogHash'], result['cisternCosting']['catalogHash'])
        self.assertEqual(len(finance['items']), len(result['cisternCosting']['items']))
        for item in finance['items']:
            for quote in item['quotes']:
                report = quote['report']
                self.assertEqual(report['status'], 'PARTIAL')
                self.assertIsNone(report['lifeCycleCost'])
                self.assertIsNone(report['comparisonKey'])
                self.assertEqual(len(report['sensitivity']), 2)
                self.assertFalse(report['budgetChargeChanged'])
                self.assertFalse(report['physicalEffectAnnualized'])
        self.assertIsNone(result['signedReductionM3'])
        self.assertIsNone(result['signedPeakReductionM3s'])
        withheld=[m for m in result['metricComparison']['metrics'] if m['status']=='WITHHELD']
        self.assertEqual(len(withheld),3)
        self.assertTrue(all(m['reason']=='UNMODELED_COVER_RAIN' and m['signedImprovement'] is None for m in withheld))
        self.assertIsNone(result['completeInstalledCostKrw'])
        self.assertIsNone(result['budgetChargedKrw'])
        folder=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        verify_graph(self, folder, result)
        manifest=json.loads((folder/'manifest.json').read_text())
        self.assertEqual(manifest['cistern-cost-catalog.json'],CATALOG_SHA256)
        self.assertEqual(manifest['cistern-quote-source.html'],design['cisternCosting']['source']['sha256'])
        self.assertEqual(json.loads((folder/'cistern-cost-snapshot.json').read_text()),design['cisternCosting'])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM budget_ledger_entries WHERE owner_id=%s',(self.owner,)).fetchone()['n'],0)
        import shutil
        from waterleague_sim.engine.swmm import ROOT
        archive=ROOT/'tmp'/('raw-metrics-withheld-'+str(identity))
        shutil.copytree(folder,archive)
        (ROOT/'tmp/raw-metrics-withheld-last-artifacts.txt').write_text(str(archive))

    def test_server_pump_request_runs_with_storage_and_preserves_native_ledger(self):
        from pathlib import Path
        from waterleague_sim.engine.swmm import ROOT
        from waterleague_sim.engine.connected_pumps import CATALOG_HASH as PUMP_HASH
        request=json.loads((self.requests/'pump-server-request.json').read_text())
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",(identity,self.owner,uuid.uuid4(),request['modelHash'],request['inputHash'],request['placements']))
        job=queue.claim(self.conn); self.assertTrue(watershed.process(self.conn,job,self.artifacts))
        row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result=json.loads(row['result']);self.assertEqual(result['numericalStatus'],'PASSED',result)
        baseline,strategy=result['cases'];self.assertEqual(baseline['pumpOperation']['pumps'],[])
        pump=strategy['pumpOperation']['pumps'][0]
        self.assertEqual(pump['linkId'],'WLPU_Pump1');self.assertEqual(pump['startCount'],3)
        self.assertGreater(pump['transferredM3'],190);self.assertEqual(pump['outsideHeadCurveSeconds'],0)
        self.assertEqual(pump['deliveryFloodingM3'],0);self.assertIsNone(pump['electricEnergyKwh'])
        self.assertEqual(strategy['connectedStorage']['numericalStatus'],'PASSED')
        self.assertEqual({n['kind'] for n in strategy['nodeFlooding']['nodes'] if not n['mapped']},{'STORAGE','JUNCTION'})
        self.assertFalse(result['rankingEligible']);self.assertIsNone(result['budgetChargedKrw'])
        directory=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        manifest=json.loads((directory/'manifest.json').read_text());self.assertEqual(manifest['pump-curve.json'],PUMP_HASH)
        for name,sha in manifest.items(): self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),sha)

    def test_server_cistern_hydraulics_preserves_native_storage_and_quotes(self):
        from pathlib import Path
        import shutil
        from waterleague_sim.engine.swmm import ROOT
        request=json.loads((self.requests/'cistern-hydraulic-server-request.json').read_text())
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),request['modelHash'],request['inputHash'],request['placements']))
        job=queue.claim(self.conn)
        self.assertTrue(watershed.process(self.conn,job,self.artifacts))
        row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result=json.loads(row['result']);design=json.loads(request['placements'])
        self.assertEqual(result['numericalStatus'],'PASSED',result)
        ledger=result['cases'][1]['networkCistern']['wholeRunLedger']['facilities'][0]
        self.assertEqual(ledger['capacityM3'],4.7)
        self.assertGreater(ledger['finalStorageM3'],2)
        self.assertEqual(ledger['floodingM3'],0)
        self.assertEqual(result['cisternCosting'],design['cisternCosting'])
        self.assertEqual(len(result['cases'][1]['facilities']),1)
        self.assertEqual(len(result['cases'][1]['nodeFlooding']['nodes']),29)
        folder=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        verify_graph(self, folder, result)
        manifest=json.loads((folder/'manifest.json').read_text())
        for name,sha in manifest.items(): self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),sha)
        changed=json.loads(request['placements']);changed['cistern']['subcatchmentId']='S1'
        raw=json.dumps(changed,sort_keys=True)
        with self.assertRaises(FloodModelError): inputs(request|{'placements':raw,'inputHash':hashlib.sha256((request['modelHash']+'\n'+raw).encode()).hexdigest()})
        archive=ROOT/'tmp'/('member-cistern-hydraulics-'+str(identity))
        shutil.copytree(folder,archive)
        (ROOT/'tmp/cistern-hydraulic-last-artifacts.txt').write_text(str(archive))

    def test_server_mixed_cistern_preserves_soil_and_impervious_allocation(self):
        import shutil
        from waterleague_sim.engine.swmm import ROOT
        request=json.loads((self.requests/'cistern-mixed-server-request.json').read_text())
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),request['modelHash'],request['inputHash'],request['placements']))
        job=queue.claim(self.conn)
        self.assertTrue(watershed.process(self.conn,job,self.artifacts))
        row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
        result=json.loads(row['result'])
        self.assertEqual(result['numericalStatus'],'PASSED',result)
        folder=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        transformed=inputs(request)[5]['networkCistern']
        verify_graph(self, folder, result)
        partition=transformed['catchmentPartition']
        self.assertEqual(transformed['schemaVersion'],2)
        self.assertAlmostEqual(partition['preservedPerviousAreaM2'],9781.255728)
        self.assertEqual(partition['captureAreaM2'],10)
        self.assertAlmostEqual(partition['originalImperviousAreaM2'],28322.584272)
        ledger=result['cases'][1]['networkCistern']['wholeRunLedger']['facilities'][0]
        self.assertEqual(ledger['capacityM3'],4.7)
        self.assertEqual(ledger['floodingM3'],0)
        self.assertGreater(ledger['finalStorageM3'],0)
        self.assertFalse(result['rankingEligible'])
        self.assertIsNone(result['budgetChargedKrw'])
        changed=json.loads(request['placements']);changed['cistern']['captureAreaM2']=30000
        raw=json.dumps(changed,sort_keys=True)
        with self.assertRaisesRegex(FloodModelError,'CAPTURE_FOOTPRINT_OVERLAP'):
            inputs(request|{'placements':raw,'inputHash':hashlib.sha256((request['modelHash']+'\n'+raw).encode()).hexdigest()})
        manifest=json.loads((folder/'manifest.json').read_text())
        for name,sha in manifest.items(): self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),sha)
        archive=ROOT/'tmp'/('member-mixed-cistern-'+str(identity))
        shutil.copytree(folder,archive)
        (ROOT/'tmp/cistern-mixed-last-artifacts.txt').write_text(str(archive))

    def test_z_server_shared_cistern_and_lid_preserve_disjoint_capture_and_original_source(self):
        import shutil
        from waterleague_sim.engine.swmm import ROOT
        from waterleague_sim.ingestion.published_network import records
        archives = []
        readback = []
        for host in ('S9','S1'):
            request=json.loads((self.requests/('cistern-shared-'+host+'-server-request.json')).read_bytes())
            identity=uuid.uuid4()
            self.conn.execute("INSERT INTO watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED',now())",
                (identity,self.owner,uuid.uuid4(),request['modelHash'],request['inputHash'],request['placements']))
            job=queue.claim(self.conn)
            self.assertTrue(watershed.process(self.conn,job,self.artifacts))
            row=self.conn.execute('SELECT * FROM watershed_experiments WHERE id=%s',(identity,)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result=json.loads(row['result'])
            self.assertEqual(result['numericalStatus'],'PASSED',result)
            folder=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
            verify_graph(self,folder,result)
            transformed=json.loads((folder/'design-transformation.json').read_bytes())
            partition=transformed['networkCistern']['catchmentPartition']
            binding=transformed['sharedCatchmentWidth']
            self.assertEqual(transformed['sourceDesign']['placements'][0]['subcatchmentId'],host)
            self.assertEqual(binding['sourceNetworkSha256'],transformed['networkCistern']['derivedNetworkSha256'])
            self.assertEqual(binding['derivedNetworkSha256'],transformed['originalSha256'])
            rows={r['tokens'][0]:r['tokens'] for r in records((folder/'strategy-input.inp').read_bytes())[1]['SUBCATCHMENTS']}
            lid=transformed['facilities'][0]
            self.assertEqual(lid['subcatchmentId'],partition['imperviousBypassId'])
            self.assertNotEqual(lid['subcatchmentId'],partition['coverId'])
            self.assertNotEqual(lid['subcatchmentId'],partition['captureId'])
            self.assertAlmostEqual(float(rows[lid['subcatchmentId']][5])/binding['remainingNonLidAreaM2'],
                                   partition['originalWidthM']/partition['originalImperviousAreaM2'])
            stored=result['cases'][1]['networkCistern']['wholeRunLedger']['facilities'][0]
            self.assertEqual(stored['capacityM3'],4.7)
            self.assertEqual(stored['floodingM3'],0)
            from waterleague_sim.engine.connected_storage import CMS_STORAGE_VOLUME_SCALE
            self.assertAlmostEqual(stored['initialStorageM3'],0.705*CMS_STORAGE_VOLUME_SCALE if host=='S1' else 0)
            self.assertEqual(stored['reuseStatus'],'NOT_CALCULATED_NO_USE_DEMAND')
            self.assertIsNone(stored['reuseM3'])
            self.assertAlmostEqual(stored['nativeCapacityM3'],4.7*CMS_STORAGE_VOLUME_SCALE)
            self.assertAlmostEqual(stored['finalAvailableM3'],stored['nativeCapacityM3']-stored['finalStorageM3'])
            self.assertEqual(result['costing'],json.loads(request['placements'])['costing'])
            self.assertFalse(result['rankingEligible']);self.assertIsNone(result['budgetChargedKrw'])
            changed=json.loads(request['placements']);changed['cistern']['captureAreaM2']=1000000
            raw=json.dumps(changed,sort_keys=True)
            with self.assertRaisesRegex(FloodModelError,'SHARED_CAPTURE_AREA_EXCEEDED'):
                inputs(request|{'placements':raw,'inputHash':hashlib.sha256((request['modelHash']+'\n'+raw).encode()).hexdigest()})
            archive=ROOT/'tmp'/('member-shared-cistern-'+str(identity))
            shutil.copytree(folder,archive);archives.append(str(archive))
            readback.append({'id':str(identity),'host':host,'artifactDirectory':str(archive),
                             'resultSha256':hashlib.sha256((archive/'result.json').read_bytes()).hexdigest()})
        (ROOT/'tmp/cistern-shared-last-artifacts.json').write_text(json.dumps(archives))
        (self.requests/'watershed-readback.json').write_text(json.dumps({'ownerId':str(self.owner),'jobs':readback}))
