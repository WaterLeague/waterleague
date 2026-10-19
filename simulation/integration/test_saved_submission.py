"""서버 저장본 확정·취소 후 제출을 실제 큐·SWMM·게시 원장으로 검증."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import unittest
import uuid
import test_worker_queue as fixture
from waterleague_sim import queue, historical


class SavedSubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.WorkerQueueTests.setUpClass.__func__(cls)
    connection = fixture.WorkerQueueTests.connection
    def setUp(self):
        fixture.WorkerQueueTests.setUp(self)

    def enqueue(self, request):
        rows = json.loads(request['placements']);head=rows[0]
        identity=uuid.uuid4()
        self.conn.execute("INSERT INTO historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',now())",
            (identity,self.owner,uuid.uuid4(),head['districtId'],request['modelHash'],request['inputHash'],request['placements']))
        rules=json.loads(head['submissionRulesRaw'])
        self.conn.execute('INSERT INTO historical_submissions(job_id,event_id,rules_hash,request_raw,cost) VALUES(%s,%s,%s,%s,%s)',
            (identity,rules['eventId'],head['submissionRulesHash'],head['submissionRequestRaw'],
             sum(json.loads(r['costSnapshotRaw'])['budgetChargeKrw'] for r in rows)))
        claimed=queue.claim(self.conn)
        self.assertEqual(claimed['id'],identity)
        self.assertTrue(historical.process(self.conn,claimed,self.artifacts))
        row=self.conn.execute('SELECT * FROM historical_experiments WHERE id=%s',(identity,)).fetchone()
        return row,self.artifacts/'historical'/str(identity)/str(claimed['lease_token'])

    def test_saved_final_design_replay_cancelled_revision_and_corrupt_lineage(self):
        source=Path(os.environ['WL_SUBMISSION_DESIGN_FIXTURE'])
        saved=json.loads(source.read_text())
        self.artifacts=Path(os.environ['WL_SUBMISSION_DESIGN_EVIDENCE']);self.artifacts.mkdir(exist_ok=False)
        (self.artifacts/'server-fixture.json').write_bytes(source.read_bytes())
        records=[]
        for key in ('original','cancelled','original'):
            request=saved[key]
            row,path=self.enqueue(request)
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result=json.loads(row['result']);head=json.loads(request['placements'])[0]
            self.assertEqual(result['submittedDesign']['snapshotSha256'],head['submissionDesignSnapshotSha256'])
            self.assertEqual(result['submittedDesign']['revision'],1 if key=='original' else 2)
            self.assertEqual((path/'submission-design.json').read_text(),head['submissionDesignSnapshotRaw'])
            self.assertEqual(len(result['districts']),2 if key=='original' else 1)
            for district in result['districts']:
                facility=district['result']['facilities'][0]
                self.assertNotIn('installedAt',facility)
                self.assertTrue(facility['initialization']['scoreExcludesWarmup'])
                self.assertEqual(facility['initialization']['warmupMinutes'],10080)
                self.assertEqual(datetime.fromisoformat(facility['initialization']['evaluationStart']),
                                 datetime.fromisoformat(result['start']))
                self.assertEqual(datetime.fromisoformat(district['result']['frames'][0]['at']),
                                 datetime.fromisoformat(result['start'])+timedelta(minutes=1))
            posted=self.conn.execute('SELECT difference_m3 FROM historical_submissions WHERE job_id=%s',(row['id'],)).fetchone()['difference_m3']
            self.assertAlmostEqual(float(posted),result['differenceM3'])
            manifest=json.loads((path/'manifest.json').read_text())
            for name,sha in manifest.items():
                self.assertEqual(hashlib.sha256((path/name).read_bytes()).hexdigest(),sha)
            records.append({'key':key,'path':str(path.relative_to(self.artifacts)),
                'differenceM3':result['differenceM3'],'designRevision':result['submittedDesign']['revision'],
                'nativeFiles':{k:v for k,v in manifest.items() if k.endswith(('.inp','.out'))}})
        self.assertEqual(records[0]['nativeFiles'],records[2]['nativeFiles'])
        self.assertEqual(records[0]['differenceM3'],records[2]['differenceM3'])
        from waterleague_sim.run_historical_submission import verify_design, HistoricalSubmissionError
        rows=json.loads(saved['original']['placements']);rules=json.loads(rows[0]['submissionRulesRaw'])
        for field,value in [('experimentInstalledAt','2022-08-08T09:59:59Z'),('areaM2',21),('costSnapshotRaw','{}')]:
            changed=deepcopy(rows);changed[-1][field]=value
            with self.subTest(field=field),self.assertRaises(HistoricalSubmissionError):verify_design(changed,rules)
        removed=deepcopy(rows)
        for field in ('submissionDesignRevision','submissionDesignSnapshotRaw','submissionDesignSnapshotSha256'):
            removed[0].pop(field)
        with self.assertRaises(HistoricalSubmissionError):verify_design(removed,rules)
        rows[-1]['experimentInstalledAt']='2022-08-08T09:59:59Z'
        body=json.dumps(rows,ensure_ascii=False,sort_keys=True)
        bad=saved['original'] | {'placements':body,'inputHash':hashlib.sha256((saved['original']['modelHash']+'\n'+body).encode()).hexdigest()}
        failed,_=self.enqueue(bad)
        self.assertEqual(failed['state'],'FAILED')
        self.assertIsNone(self.conn.execute('SELECT difference_m3 FROM historical_submissions WHERE job_id=%s',(failed['id'],)).fetchone()['difference_m3'])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM budget_ledger_entries').fetchone()['n'],0)
        (self.artifacts/'verification.json').write_text(json.dumps({'classification':'SAVED_DESIGN_FINAL_SUBMISSION_INDEPENDENT_SURFACES',
            'productionPublished':False,'cases':records,'sameInputNativeReplay':True,
            'corruptLineageRejected':True,'limitations':['격리 DB 시험 회원; 연결 침수·당시 자산 복원·공식 총점 아님']},ensure_ascii=False,indent=2)+'\n')
