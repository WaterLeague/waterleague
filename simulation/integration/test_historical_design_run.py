"""서버의 두 구 저장 설계 요청을 실제 네이티브 워커로 실행·재생."""
import hashlib
import json
import os
from pathlib import Path
import unittest
import uuid
import test_worker_queue as fixture
from waterleague_sim import queue, historical

class HistoricalDesignRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.WorkerQueueTests.setUpClass.__func__(cls)
    connection = fixture.WorkerQueueTests.connection
    def setUp(self):
        fixture.WorkerQueueTests.setUp(self)

    def test_server_frozen_two_district_design_and_native_replay(self):
        source = Path(os.environ['WL_DESIGN_RUN_FIXTURE'])
        saved = json.loads(source.read_text())
        self.artifacts = Path(os.environ['WL_DESIGN_RUN_EVIDENCE'])
        self.artifacts.mkdir(exist_ok=False)
        (self.artifacts/'server-requests.json').write_bytes(source.read_bytes())
        rows = saved['requests']
        self.assertEqual(len(rows), 2)
        records = []
        for index, request in enumerate([*rows, rows[0]]):
            placements = json.loads(request['placements'])
            head = placements[0]
            self.assertEqual(head['designSnapshotSha256'], saved['design']['snapshotSha256'])
            self.assertEqual(hashlib.sha256(head['designSnapshotRaw'].encode()).hexdigest(), head['designSnapshotSha256'])
            identity = uuid.uuid4()
            self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
                (identity,self.owner,uuid.uuid4(),head['districtId'],request['modelHash'],request['inputHash'],request['placements']))
            job = queue.claim(self.conn)
            self.assertEqual(job['id'],identity)
            self.assertTrue(historical.process(self.conn,job,self.artifacts))
            row = self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result = json.loads(row['result'])
            self.assertEqual(result['temporalPolicy'],'INSTALLATION_TIME_EXPERIMENT_V1')
            facility = result['facilities'][0]
            self.assertEqual(facility['installedAt'],head['installedAt'])
            self.assertEqual(facility['frames'][0]['differenceM3'],0)
            self.assertEqual(facility['frames'][0]['at'],head['installedAt'])
            self.assertTrue(facility['initialization']['scoreExcludesWarmup'])
            self.assertEqual(facility['initialization']['warmupMinutes'],10080)
            root = self.artifacts/'historical'/str(identity)/str(job['lease_token'])
            manifest = json.loads((root/'manifest.json').read_text())
            for name, expected in manifest.items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), expected)
            records.append({'index':index,'districtId':head['districtId'],'installedAt':head['installedAt'],
                'resultPath':str((root/'result.json').relative_to(self.artifacts)),
                'resultSha256':hashlib.sha256((root/'result.json').read_bytes()).hexdigest(),
                'differenceM3':result['differenceM3'],
                'nativeFiles':{k:v for k,v in manifest.items() if k.endswith(('.inp','.out'))}})
        self.assertEqual(records[0]['nativeFiles'],records[2]['nativeFiles'])
        self.assertEqual(records[0]['resultSha256'],records[2]['resultSha256'])
        self.assertNotEqual(records[0]['districtId'],records[1]['districtId'])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM historical_submissions').fetchone()['n'],0)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM budget_ledger_entries').fetchone()['n'],0)
        (self.artifacts/'verification.json').write_text(json.dumps({'classification':'SAVED_DESIGN_INDEPENDENT_SURFACES_TEST',
            'rankingEligible':False,'cases':records,'sameInputNativeReplay':True,
            'limitation':'두 구의 독립 표면 실제 엔진 실행; 연결 유역·현장 검증 아님'},ensure_ascii=False,indent=2)+'\n')
