"""격리 DB의 회원 관망 요청·실제 공개 입력 계산·임대 보존 검증."""
import hashlib
import json
import unittest
import uuid
import test_worker_queue as fixture
from waterleague_sim import queue, watershed
from waterleague_sim.run_watershed_job import CATALOG, CATALOG_HASH, inputs
from waterleague_sim.engine.flood_errors import FloodModelError


class WatershedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.WorkerQueueTests.setUpClass.__func__(cls)
    connection=fixture.WorkerQueueTests.connection
    def setUp(self):
        fixture.WorkerQueueTests.setUp(self)

    def test_public_network_design_job_and_bound_artifacts(self):
        catalog=json.loads(CATALOG.read_text())
        design={'schemaVersion':1,'basis':catalog['designBasis'],'placements':[
            {'id':'Bio1','facilityType':'BIORETENTION','subcatchmentId':'S1','areaM2':100,
             'replacedImperviousM2':100,'treatedImperviousM2':1000,'initialSaturationPercent':0,
             'parameters':catalog['templates']['BIORETENTION']['parameters']}]}
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
        self.assertFalse(result['rankingEligible'])
        self.assertIsNone(result['completeInstalledCostKrw'])
        self.assertLess(result['signedReductionM3']['outflowM3'],0)
        self.assertGreater(result['signedReductionM3']['floodingM3'],0)
        directory=self.artifacts/'watersheds'/str(identity)/str(job['lease_token'])
        manifest=json.loads((directory/'manifest.json').read_text())
        for name,sha in manifest.items():
            self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),sha)
            if name!='result.json': self.assertEqual(result['artifactFiles'][name],sha)
        self.assertEqual(manifest['catalog.json'],CATALOG_HASH)
        self.assertIn('strategy/network.out',manifest)
        self.assertFalse(queue.finish(self.conn,job,'SUCCEEDED',{'stale':True},None))
        request={'modelHash':CATALOG_HASH,'inputHash':digest,'placements':raw}
        with self.assertRaises(FloodModelError): inputs(request | {'inputHash':'0'*64})
        design['placements'][0]['parameters']['nativeSeepageMmH']=1000
        changed=json.dumps(design,sort_keys=True)
        with self.assertRaises(FloodModelError): inputs(request | {'placements':changed,'inputHash':hashlib.sha256((CATALOG_HASH+'\n'+changed).encode()).hexdigest()})
