"""비회원 API의 고정 입력을 실제 큐·SWMM으로 계산하고 재생 대조."""
import hashlib
import json
import os
import unittest
import uuid
from pathlib import Path
import test_worker_queue as queue_fixture
from waterleague_sim import queue, historical

class GuestHistoricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        queue_fixture.WorkerQueueTests.setUpClass.__func__(cls)
    connection = queue_fixture.WorkerQueueTests.connection
    def setUp(self):
        queue_fixture.WorkerQueueTests.setUp(self)

    def test_guest_native_calculation_and_identical_replay_without_ranking(self):
        request=json.loads(Path(os.environ['WL_GUEST_FIXTURE']).read_text())
        artifacts=Path(os.environ['WL_GUEST_EVIDENCE'])
        guest='f'*64
        outputs=[]
        hashes=[]
        for _ in range(2):
            identity=uuid.uuid4()
            self.conn.execute("INSERT INTO historical_experiments(id,guest_key,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,'2419953',%s,%s,%s,'QUEUED',now())",(identity,guest,uuid.uuid4(),request['modelHash'],request['inputHash'],request['placements']))
            job=queue.claim(self.conn)
            self.assertIsNone(job['owner_id'])
            self.assertTrue(historical.process(self.conn,job,artifacts))
            row=self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result=json.loads(row['result'])
            self.assertEqual(result['temporalPolicy'],'INSTALLATION_TIME_EXPERIMENT_V1')
            self.assertEqual(result['frames'][0]['differenceM3'],0)
            self.assertEqual(result['frames'][1]['differenceM3'],0)
            self.assertEqual(result['frames'][-1]['differenceM3'],result['differenceM3'])
            self.assertEqual(result['facilities'][0]['initialization']['warmupMinutes'],10080)
            path=artifacts/'historical'/str(identity)/str(job['lease_token'])
            manifest=json.loads((path/'manifest.json').read_text())
            for name,digest in manifest.items():
                self.assertEqual(hashlib.sha256((path/name).read_bytes()).hexdigest(),digest)
            hashes.append({k:v for k,v in manifest.items() if k.endswith(('.inp','.out'))})
            outputs.append(result)
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(hashes[0],hashes[1])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM historical_submissions').fetchone()['n'],0)
