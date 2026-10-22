"""단일 키 호출 상한·차단·저장 원문 재사용을 외부 호출 없이 검사."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.message import Message
from io import BytesIO
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from waterleague_sim.ingestion import live, request_store as store


class KmaSingleKeyTests(unittest.TestCase):
    key = 'PRIMARY_TEST_SECRET'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {'EXTERNAL_REQUEST_STATE_DIR': temporary.name,
            'KMA_API_KEY_BACKUP': 'RETIRED_TEST_SECRET'})
        env.start(); self.addCleanup(env.stop)
        self.opener = Mock()
        opener = patch.object(live, 'build_opener', return_value=self.opener)
        opener.start(); self.addCleanup(opener.stop)
        self.sent = []

    def transport(self, status=None):
        def send(url, **kwargs):
            self.sent.append(parse_qs(urlsplit(url).query)['authKey'][0])
            if status:
                raise HTTPError(url, status, 'test', Message(), BytesIO(b'error'))
            return BytesIO(b'observed response')
        self.opener.open.side_effect = send

    def fetch(self, station='421'):
        return live.shared_response(live.ENDPOINT, {'stn':station}, self.key)

    def test_concurrent_consumers_share_body_and_acquisition_time(self):
        self.transport()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.fetch(), range(6)))
        self.assertEqual(self.sent, [self.key])
        self.assertEqual({r[0] for r in results}, {b'observed response'})
        self.assertEqual(len({r[1]['fetchedAt'] for r in results}), 1)

    def test_eighteen_thousand_limit_keeps_headroom_and_cached_response(self):
        day, _ = store.period(datetime.now().timestamp())
        with store.database() as db:
            db.execute('INSERT INTO budget VALUES(?,?,17999,0,0)', (store.identity(self.key),day))
        self.transport()
        first = self.fetch()
        self.assertEqual(self.fetch()[0], first[0])
        self.assertFalse(store.available(self.key))
        with self.assertRaisesRegex(live.LiveSourceError, 'KMA_REQUEST_BUDGET_BLOCKED'):
            self.fetch('108')
        self.assertEqual(self.sent, [self.key])
        with store.database() as db:
            self.assertEqual(db.execute('SELECT calls FROM budget').fetchall(), [(18000,)])

    def test_byte_limit_blocks_before_network_and_preserves_usage(self):
        day, _ = store.period(datetime.now().timestamp())
        with store.database() as db:
            db.execute('INSERT INTO budget VALUES(?,?,1,4496000001,0)', (store.identity(self.key),day))
        self.assertFalse(store.available(self.key))
        with self.assertRaisesRegex(live.LiveSourceError, 'KMA_REQUEST_BUDGET_BLOCKED'):
            self.fetch()
        self.opener.open.assert_not_called()

    def test_access_denied_does_not_use_retired_backup_or_repeat(self):
        self.transport(403)
        for station in ('421', '108'):
            with self.assertRaises(live.LiveSourceError): self.fetch(station)
        self.assertEqual(self.sent, [self.key])
        self.assertFalse(store.available(self.key))

    def test_midnight_reopens_primary_and_keeps_original_cached_time(self):
        before = datetime(2026,10,22,23,59,tzinfo=store.KST).timestamp()
        self.transport()
        with patch.object(store.time, 'time', return_value=before):
            first = self.fetch()
            store.block(self.key,403)
            with self.assertRaises(live.LiveSourceError): self.fetch('108')
        with patch.object(store.time, 'time', return_value=before+61):
            cached = self.fetch()
            self.fetch('108')
        self.assertEqual(first[0], cached[0])
        self.assertEqual(first[1]['fetchedAt'], cached[1]['fetchedAt'])
        self.assertEqual(self.sent, [self.key,self.key])

    def test_timeout_stops_followup_requests_for_shared_backoff(self):
        self.opener.open.side_effect = TimeoutError()
        for station in ('421','108'):
            with self.assertRaises(live.LiveSourceError): self.fetch(station)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_key_echo_is_never_cached(self):
        self.opener.open.return_value = BytesIO(self.key.encode())
        with self.assertRaisesRegex(live.LiveSourceError,'KMA_RESPONSE_INVALID'): self.fetch()
        with store.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM responses WHERE raw IS NOT NULL').fetchone()[0],0)

    def test_lost_lease_does_not_make_external_calls(self):
        heartbeat = Mock(side_effect=ValueError('LIVE_LEASE_LOST'))
        with self.assertRaisesRegex(ValueError,'LIVE_LEASE_LOST'):
            live.shared_response(live.ENDPOINT,{},self.key,heartbeat)
        self.opener.open.assert_not_called()

    def test_blocked_worker_does_not_claim_or_create_physics_jobs(self):
        from waterleague_sim import shared_physics
        store.block(self.key,403)
        with patch.dict(os.environ, {'KMA_API_KEY':self.key}), patch.object(shared_physics,'claim') as claim:
            self.assertFalse(shared_physics.run_once(Mock(),None))
        claim.assert_not_called()
