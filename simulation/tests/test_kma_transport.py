"""공급자 오류 뒤의 추가 호출 차단·원문 보존·임대 검사."""
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from io import BytesIO
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from waterleague_sim.ingestion import evaporation, live, request_store

class KmaTransportTests(unittest.TestCase):
    start = datetime(2026,10,14,1,tzinfo=live.KST)
    key = 'TEST_ONLY_SECRET'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.env = patch.dict(os.environ, {'EXTERNAL_REQUEST_STATE_DIR':self.temporary.name})
        self.env.start(); self.addCleanup(self.env.stop)

    def error(self, status, retry_after=None):
        headers=Message()
        if retry_after is not None: headers['Retry-After']=retry_after
        return HTTPError('https://apihub.kma.go.kr/',status,'test',headers,BytesIO(b'error'))

    def test_failure_blocks_other_facilities_without_retries_or_range_splitting(self):
        for error in (TimeoutError(),self.error(403),self.error(429,'120'),self.error(503)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory, \
                    patch.dict(os.environ,{'EXTERNAL_REQUEST_STATE_DIR':directory}):
                opener=Mock();opener.open.side_effect=error
                with patch.object(live,'build_opener',return_value=opener):
                    with self.assertRaises(live.LiveSourceError) as caught:
                        live.observed_forcing('421',self.start,self.start+timedelta(hours=7),self.key)
                    self.assertFalse(caught.exception.can_reduce_range)
                    with self.assertRaisesRegex(live.LiveSourceError,'KMA_REQUEST_BUDGET_BLOCKED'):
                        evaporation.fetch(evaporation.STATION_URL,{},self.key)
                self.assertEqual(opener.open.call_count,1)
                self.assertFalse(request_store.available(self.key))

    def test_same_observation_shares_original_bytes_timestamp_and_one_call(self):
        opener=Mock();opener.open.return_value=BytesIO(b'observed response')
        with patch.object(live,'build_opener',return_value=opener):
            a=live.fetch_range('421',self.start,self.start+timedelta(hours=1),self.key)
            b=live.fetch_range('421',self.start,self.start+timedelta(hours=1),self.key)
        self.assertEqual(a,b)
        self.assertEqual(opener.open.call_count,1)
        self.assertNotIn(self.key,str(a[1]))
        self.assertNotIn('authKey',a[1]['parameters'])

    def test_lease_is_checked_before_external_request(self):
        opener=Mock();heartbeat=Mock(side_effect=ValueError('LIVE_LEASE_LOST'))
        with patch.object(live,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'LIVE_LEASE_LOST'):
                evaporation.fetch(evaporation.STATION_URL,{},self.key,heartbeat)
        opener.open.assert_not_called()

    def test_invalid_or_secret_response_is_not_saved(self):
        for raw in (self.key.encode(),b'x'*4_000_001):
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'EXTERNAL_REQUEST_STATE_DIR':directory}):
                opener=Mock();opener.open.return_value=BytesIO(raw)
                with patch.object(live,'build_opener',return_value=opener):
                    with self.assertRaisesRegex(live.LiveSourceError,'KMA_RESPONSE_INVALID'):
                        evaporation.fetch(evaporation.STATION_URL,{},self.key)
                with request_store.database() as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM responses WHERE raw IS NOT NULL').fetchone()[0],0)

    def test_retry_after_seconds_and_http_date_keep_provider_wait(self):
        self.assertEqual(live.retry_seconds('120'),120)
        self.assertEqual(live.retry_seconds('0'),60)
        future=format_datetime(datetime.now(timezone.utc)+timedelta(minutes=3),usegmt=True)
        self.assertGreater(live.retry_seconds(future),178)
        self.assertEqual(live.retry_seconds('invalid'),60)
