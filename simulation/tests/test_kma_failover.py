"""키별 한도·전환·동시 원문 공유를 실제 외부 호출 없이 검사."""
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


class KmaFailoverTests(unittest.TestCase):
    primary = 'PRIMARY_TEST_SECRET'
    backup = 'BACKUP_TEST_SECRET'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {'EXTERNAL_REQUEST_STATE_DIR': temporary.name,
            'KMA_API_KEY_BACKUP': self.backup})
        env.start(); self.addCleanup(env.stop)
        self.opener = Mock()
        opener = patch.object(live, 'build_opener', return_value=self.opener)
        opener.start(); self.addCleanup(opener.stop)
        self.sent = []

    def transport(self, fail_primary=None, fail_backup=None):
        def send(url, **kwargs):
            key = parse_qs(urlsplit(url).query)['authKey'][0]
            self.sent.append(key)
            failure = fail_primary if key == self.primary else fail_backup
            if failure:
                raise HTTPError(url, failure, 'test', Message(), BytesIO(b'error'))
            return BytesIO(b'observed response')
        self.opener.open.side_effect = send

    def fetch(self, station='421'):
        return live.shared_response(live.ENDPOINT, {'stn':station}, self.primary)

    def test_primary_success_never_uses_backup(self):
        self.transport()
        self.fetch()
        self.assertEqual(self.sent, [self.primary])

    def test_primary_failure_uses_backup_once_and_shares_original_response(self):
        self.transport(fail_primary=403)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.fetch(), range(6)))
        self.assertEqual(self.sent, [self.primary,self.backup])
        self.assertEqual({r[0] for r in results}, {b'observed response'})
        self.assertEqual(len({r[1]['fetchedAt'] for r in results}), 1)
        self.assertNotIn(self.backup, str(results))
        self.assertFalse(store.available(self.primary))
        self.assertTrue(store.kma_available(self.primary))
        self.fetch('108')
        self.assertEqual(self.sent, [self.primary,self.backup,self.backup])

    def test_each_key_allows_twenty_thousand_calls_and_never_exceeds(self):
        day,_ = store.period(datetime.now().timestamp())
        with store.database() as db:
            for key in (self.primary,self.backup):
                db.execute('INSERT INTO budget VALUES(?,?,19999,0,0)', (store.identity(key),day))
        self.transport()
        self.fetch('1'); self.fetch('2')
        with self.assertRaisesRegex(live.LiveSourceError, 'KMA_REQUEST_BUDGET_BLOCKED'):
            self.fetch('3')
        self.assertEqual(self.sent, [self.primary,self.backup])
        with store.database() as db:
            self.assertEqual(db.execute('SELECT calls FROM budget').fetchall(), [(20000,),(20000,)])
        self.assertFalse(store.kma_available(self.primary))

    def test_both_keys_failed_are_not_retried_by_other_requests(self):
        self.transport(fail_primary=403,fail_backup=503)
        for station in ('421','108'):
            with self.assertRaises(live.LiveSourceError): self.fetch(station)
        self.assertEqual(self.sent, [self.primary,self.backup])
        self.assertFalse(store.kma_available(self.primary))

    def test_midnight_restores_primary_priority_and_cache_survives_switch(self):
        before = datetime(2026,10,22,23,59,tzinfo=store.KST).timestamp()
        self.transport()
        with patch.object(store.time,'time',return_value=before):
            store.block(self.primary,403)
            first = self.fetch()
        with patch.object(store.time,'time',return_value=before+61):
            cached = self.fetch()
            self.fetch('108')
        self.assertEqual(first[0], cached[0])
        self.assertEqual(first[1]['fetchedAt'], cached[1]['fetchedAt'])
        self.assertEqual(self.sent, [self.backup,self.primary])

    def test_optional_and_duplicate_backup_do_not_repeat_primary(self):
        for backup in ('',self.primary):
            with self.subTest(backup=bool(backup)), patch.dict(os.environ,{'KMA_API_KEY_BACKUP':backup}):
                self.assertEqual(store.kma_keys(self.primary), (self.primary,))

    def test_timeout_uses_backup_but_invalid_request_does_not(self):
        self.opener.open.side_effect = [TimeoutError(),BytesIO(b'observed response')]
        self.fetch()
        self.assertEqual(self.opener.open.call_count,2)
        self.opener.open.reset_mock()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'EXTERNAL_REQUEST_STATE_DIR':directory}):
            self.transport(fail_primary=400)
            with self.assertRaises(live.LiveSourceError): self.fetch()
            self.assertEqual(self.sent,[self.primary])

    def test_key_echo_is_never_cached_and_does_not_trigger_backup(self):
        self.opener.open.return_value = BytesIO(self.backup.encode())
        with self.assertRaisesRegex(live.LiveSourceError,'KMA_RESPONSE_INVALID'): self.fetch()
        self.assertEqual(self.opener.open.call_count,1)
        with store.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM responses WHERE raw IS NOT NULL').fetchone()[0],0)

    def test_lost_lease_does_not_make_calls_with_either_key(self):
        heartbeat = Mock(side_effect=ValueError('LIVE_LEASE_LOST'))
        with self.assertRaisesRegex(ValueError,'LIVE_LEASE_LOST'):
            live.shared_response(live.ENDPOINT,{},self.primary,heartbeat)
        self.opener.open.assert_not_called()
