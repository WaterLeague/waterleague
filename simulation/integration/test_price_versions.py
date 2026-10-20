"""격리 DB의 이전·환산 단가를 실제 관측 계산과 원가 보관까지 대조."""
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg.rows import dict_row
from waterleague_sim import shared_physics, historical, queue
from waterleague_sim.forcing.game_climate import load
from waterleague_sim.spatial import game_catalog
from waterleague_sim.ingestion import antecedent as antecedent_module


class PriceVersionWorkerTests(unittest.TestCase):
    def test_old_and_indexed_costs_reach_weekly_experiment_and_submission(self):
        fixture=json.loads(Path(os.environ['WL_PRICE_FIXTURE']).read_bytes())
        root=Path(os.environ['WL_PRICE_EVIDENCE'])
        root.mkdir(exist_ok=False)
        observed=json.loads(game_catalog.forcing(fixture['forcingHash']))
        pet, prior=load(fixture['forcingHash'],observed,root/'observed')
        start=datetime.fromisoformat(observed['rainfall']['start'])
        sources={}
        for source in (root/'observed').glob('*.txt'):
            raw=source.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
            sources[sha]=(raw,{'sha256':sha,'purpose':'ARCHIVED_OBSERVATIONS_ISOLATED_PRICE_TEST'})
        archive=list(sources.values())
        def forcing(station,begin,end,key,heartbeat=None):
            if heartbeat: heartbeat()
            self.assertEqual(station,observed['rainfall']['stationId'])
            i,j=[int((v-start).total_seconds()/60) for v in (begin,end)]
            values=[{'end':(start+timedelta(minutes=k+1)).isoformat(),'depthMm':depth,
                'method':'ARCHIVED_OBSERVED_TEST_REPLAY','weather':{}}
                for k,depth in enumerate(observed['rainfall']['depthsMm']) if i<=k<j]
            return {'stationId':station,'start':begin.isoformat(),'end':end.isoformat(),
                'intervalSeconds':60,'observations':values,'overlapObservations':[],
                'sourceHashes':[observed['rainfall']['sourceHash']],
                'evidence':'ARCHIVED_OBSERVED_TEST_REPLAY'},archive
        def evaporation(begin,end,key,heartbeat=None):
            if heartbeat: heartbeat()
            i,j=[int((v-start).total_seconds()/60) for v in (begin,end)]
            return pet|{'ratesMmDay':pet['ratesMmDay'][i:j],'hours':[]},archive
        def antecedent(station,end,key,heartbeat=None):
            if heartbeat: heartbeat()
            self.assertEqual(end,start)
            return prior,archive
        with psycopg.connect(os.environ['WL_WORKER_TEST_DSN'],autocommit=True,row_factory=dict_row) as db:
            self.assertRegex(db.info.dbname,r'^waterleague_[a-z_]+_test_[a-f0-9]{32}$')
            ids=[uuid.UUID(value) for value in fixture['installations']]
            before=db.execute('SELECT id,cost,cost_snapshot,cost_snapshot_sha256 FROM shared_installations WHERE id=ANY(%s) ORDER BY id',(ids,)).fetchall()
            ledger=db.execute('SELECT id,amount_krw FROM budget_ledger_entries WHERE installation_id=ANY(%s) ORDER BY id',(ids,)).fetchall()
            db.execute('UPDATE shared_installations SET installed_at=%s,season_ends_at=%s WHERE id=ANY(%s)',
                (start,start+timedelta(minutes=60),ids))
            weekly=[]
            with patch.object(shared_physics,'observed_forcing',side_effect=forcing), \
                 patch.object(shared_physics,'observed_evaporation',side_effect=evaporation), \
                 patch.object(antecedent_module,'fetch',side_effect=antecedent):
                for _ in ids:
                    job=shared_physics.claim(db)
                    self.assertIn(job['installation']['id'],ids)
                    self.assertTrue(shared_physics.process(db,job,root))
                    stored=db.execute('SELECT state,result,error_code FROM shared_physics_jobs WHERE id=%s',(job['id'],)).fetchone()
                    self.assertEqual(stored['state'],'SUCCEEDED',stored['error_code'])
                    result=json.loads(stored['result'])
                    directory=root/'shared-physics'/str(job['id'])/str(job['lease_token'])
                    raw=(directory/'cost-snapshot.json').read_bytes()
                    record={'status':'RECORDED','sha256':hashlib.sha256(raw).hexdigest(),'estimate':json.loads(raw)}
                    self.assertEqual(result['designContract']['cost']['snapshotSha256'],record['sha256'])
                    self.assertEqual(json.loads((directory/'manifest.json').read_bytes())['cost-snapshot.json'],record['sha256'])
                    original=next(r for r in before if r['id']==job['installation']['id'])
                    self.assertEqual(record['sha256'],original['cost_snapshot_sha256'])
                    self.assertEqual(record['estimate'],json.loads(original['cost_snapshot']))
                    weekly.append(record)
            expected={row['item']['cellId']:row for row in fixture['design']['snapshot']['placements']}
            completed={}
            for _ in range(3):
                job=queue.claim(db)
                self.assertIn(str(job['id']),[fixture['experimentId'],fixture['submissionId'],fixture['guestJobId']])
                frozen={row['cellId']:row for row in json.loads(job['placements'])}
                if str(job['id'])!=fixture['guestJobId']:
                    for cell,row in frozen.items():
                        self.assertEqual(row['costSnapshotRaw'],expected[cell]['costSnapshotRaw'])
                        self.assertEqual(row['costSnapshotSha256'],expected[cell]['costSnapshotSha256'])
                self.assertTrue(historical.process(db,job,root))
                row=db.execute('SELECT state,result,error_code FROM historical_experiments WHERE id=%s',(job['id'],)).fetchone()
                self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
                result=json.loads(row['result'])
                facilities=result['districts'][0]['result']['facilities'] if str(job['id'])==fixture['submissionId'] else result['facilities']
                total=Decimal(0)
                for facility in facilities:
                    original=frozen[facility['cellId']]
                    record=facility['costRecord']
                    self.assertEqual(record['sha256'],original['costSnapshotSha256'])
                    self.assertEqual(record['estimate'],json.loads(original['costSnapshotRaw']))
                    total+=Decimal(str(record['estimate']['budgetChargeKrw']))
                self.assertEqual(total,Decimal(1100000 if str(job['id'])==fixture['guestJobId'] else fixture['expectedTotalKrw']))
                completed[str(job['id'])]=result
            after=db.execute('SELECT id,cost,cost_snapshot,cost_snapshot_sha256 FROM shared_installations WHERE id=ANY(%s) ORDER BY id',(ids,)).fetchall()
            self.assertEqual(before,after)
            self.assertEqual(ledger,db.execute('SELECT id,amount_krw FROM budget_ledger_entries WHERE installation_id=ANY(%s) ORDER BY id',(ids,)).fetchall())
            score=db.execute('SELECT difference_m3,cost FROM historical_submissions WHERE job_id=%s',(uuid.UUID(fixture['submissionId']),)).fetchone()
            self.assertEqual(score['cost'],Decimal(fixture['expectedTotalKrw']))
            self.assertIsNotNone(score['difference_m3'])
            (root/'verification.json').write_text(json.dumps({'status':'PASS','classification':'ISOLATED_DATABASE_OBSERVED_SWMM_PRICE_VERSION_TEST',
                'expectedTotalKrw':fixture['expectedTotalKrw'],'weeklyCostRecords':weekly,
                'storedCostsAndLedgerUnchanged':True,'experimentAndSubmissionCompleted':True,
                'fieldValidated':False},ensure_ascii=False,indent=2)+'\n')
