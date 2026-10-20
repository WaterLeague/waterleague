"""격리 DB의 일반 설치·예산·보관 실관측 워커·제출 원장 연결 검사."""
from datetime import datetime, timedelta
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


class CisternGameWorkflowTests(unittest.TestCase):
    def test_real_observations_weekly_and_final_submission(self):
        dsn = os.environ['WL_WORKER_TEST_DSN']
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as db:
            self.assertRegex(db.info.dbname, r'^waterleague_[a-z_]+_test_[a-f0-9]{32}$')
            fixture = json.loads(Path(os.environ['WL_CISTERN_GAME_FIXTURE']).read_bytes())
            root = Path(os.environ['WL_CISTERN_GAME_EVIDENCE'])
            root.mkdir(exist_ok=False)
            observed = json.loads(game_catalog.forcing(fixture['forcingHash']))
            pet, prior = load(fixture['forcingHash'], observed, root / 'observed')
            start = datetime.fromisoformat(observed['rainfall']['start'])
            sources = {}
            for source in (root / 'observed').glob('*.txt'):
                raw = source.read_bytes()
                sha = hashlib.sha256(raw).hexdigest()
                sources[sha] = (raw, {'sha256': sha, 'purpose': 'ARCHIVED_OBSERVATIONS_ISOLATED_TEST'})
            archive = list(sources.values())

            def forcing(station, begin, end, key, heartbeat=None):
                if heartbeat: heartbeat()
                self.assertEqual(station, observed['rainfall']['stationId'])
                i, j = [int((v - start).total_seconds() / 60) for v in (begin, end)]
                values = [{'end': (start + timedelta(minutes=k + 1)).isoformat(), 'depthMm': depth,
                    'method': 'ARCHIVED_OBSERVED_TEST_REPLAY', 'weather': {}}
                    for k, depth in enumerate(observed['rainfall']['depthsMm']) if i <= k < j]
                return {'stationId': station, 'start': begin.isoformat(), 'end': end.isoformat(),
                    'intervalSeconds': 60, 'observations': values, 'overlapObservations': [],
                    'sourceHashes': [observed['rainfall']['sourceHash']],
                    'evidence': 'ARCHIVED_OBSERVED_TEST_REPLAY'}, archive

            def evaporation(begin, end, key, heartbeat=None):
                if heartbeat: heartbeat()
                i, j = [int((v - start).total_seconds() / 60) for v in (begin, end)]
                return pet | {'ratesMmDay': pet['ratesMmDay'][i:j], 'hours': []}, archive

            def antecedent(station, end, key, heartbeat=None):
                if heartbeat: heartbeat()
                self.assertEqual(end, start)
                return prior, archive

            installation = uuid.UUID(fixture['installationId'])
            # 시험 DB에서만 기존 관측 시각으로 이동해 같은 운영 워커를 재생한다.
            db.execute("UPDATE shared_installations SET installed_at=%s,season_ends_at=%s WHERE id=%s",
                (start, start + timedelta(minutes=60), installation))
            from waterleague_sim.ingestion import antecedent as antecedent_module
            with patch.object(shared_physics, 'observed_forcing', side_effect=forcing), \
                 patch.object(shared_physics, 'observed_evaporation', side_effect=evaporation), \
                 patch.object(antecedent_module, 'fetch', side_effect=antecedent):
                job = shared_physics.claim(db)
                self.assertEqual(job['installation']['id'], installation)
                self.assertTrue(shared_physics.process(db, job, root))
            row = db.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (job['id'],)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            weekly = json.loads(row['result'])
            self.assertEqual(weekly['cistern']['capacityM3'], 2.35)
            self.assertEqual(weekly['initialization']['warmupMinutes'], 10080)
            self.assertIsNone(weekly['cistern']['reuseM3'])
            self.assertEqual(db.execute('SELECT sum(evaluated_minutes) AS n FROM shared_weekly_scores WHERE installation_id=%s',
                (installation,)).fetchone()['n'], 60)
            submitted = queue.claim(db)
            self.assertEqual(str(submitted['id']), fixture['submissionId'])
            self.assertTrue(historical.process(db, submitted, root))
            result = db.execute('SELECT * FROM historical_experiments WHERE id=%s', (submitted['id'],)).fetchone()
            self.assertEqual(result['state'], 'SUCCEEDED', result['error_code'])
            final = json.loads(result['result'])
            facility = final['districts'][0]['result']['facilities'][0]
            self.assertEqual(facility['cistern']['capacityM3'], 2.35)
            self.assertEqual(facility['initialization']['warmupMinutes'], 10080)
            self.assertEqual(facility['costRecord']['estimate']['budgetChargeKrw'], fixture['costKrw'])
            self.assertIsNone(facility['cistern']['reuseM3'])
            self.assertGreater(facility['cistern']['overflowM3'], 0)
            score = db.execute('SELECT difference_m3 FROM historical_submissions WHERE job_id=%s',
                (submitted['id'],)).fetchone()['difference_m3']
            self.assertAlmostEqual(float(score), final['differenceM3'])
            (root / 'verification.json').write_text(json.dumps({
                'status': 'PASS', 'facilityType': 'RAINWATER_CISTERN',
                'classification': 'ISOLATED_DATABASE_REAL_OBSERVATION_REPLAY',
                'fieldValidated': False, 'forcingHash': fixture['forcingHash'],
                'weeklyMinutes': 60, 'warmupMinutes': 10080, 'budgetChargeKrw': fixture['costKrw'],
                'historicalCistern': facility['cistern'], 'differenceM3': final['differenceM3'],
                'weeklyResult': weekly, 'designContract': facility['designContract'],
                'installationAndBudgetVerified': True, 'submissionAndScorePublished': True,
            }, ensure_ascii=False, indent=2) + '\n')
