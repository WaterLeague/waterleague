"""실패한 관측을 만들지 않고 한정된 재조회·임대 확인을 적용하는 검사."""
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from io import BytesIO
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from waterleague_sim.ingestion import evaporation, live


class KmaTransportTests(unittest.TestCase):
    start = datetime(2026, 10, 14, 1, tzinfo=live.KST)
    key = 'TEST_ONLY_SECRET'

    def error(self, status, retry_after=None):
        headers = Message()
        if retry_after is not None:
            headers['Retry-After'] = retry_after
        return HTTPError('https://apihub.kma.go.kr/?authKey='+self.key,
                         status, 'test', headers, BytesIO(b'error'))

    def test_transient_failure_retries_identical_get_and_preserves_received_bytes(self):
        for error in (TimeoutError(), self.error(503)):
            with self.subTest(error=type(error).__name__):
                opener, heartbeat = Mock(), Mock()
                opener.open.side_effect = [error, BytesIO(b'observed response')]
                with patch.object(live, 'build_opener', return_value=opener), \
                        patch.object(live.time, 'sleep') as sleep:
                    raw, metadata = live.fetch_range(
                        '421', self.start, self.start+timedelta(hours=1), self.key, heartbeat)
                self.assertEqual(raw, b'observed response')
                self.assertEqual(opener.open.call_count, 2)
                self.assertEqual(opener.open.call_args_list[0], opener.open.call_args_list[1])
                self.assertEqual(heartbeat.call_count, 3)
                sleep.assert_called_once()
                self.assertNotIn(self.key, str(metadata))
                self.assertNotIn('authKey', metadata['parameters'])

    def test_authentication_redirect_certificate_and_invalid_response_are_not_retried(self):
        for error in (self.error(401), self.error(403), self.error(302), self.error(404),
                      URLError(ssl.SSLCertVerificationError('test certificate'))):
            with self.subTest(error=str(type(error))):
                opener = Mock()
                opener.open.side_effect = error
                with patch.object(live, 'build_opener', return_value=opener), \
                        patch.object(live.time, 'sleep') as sleep:
                    with self.assertRaises(live.LiveSourceError) as caught:
                        live.fetch_range('421', self.start, self.start+timedelta(hours=1), self.key)
                self.assertNotIn(self.key, str(caught.exception))
                self.assertEqual(opener.open.call_count, 1)
                sleep.assert_not_called()
        for raw in (self.key.encode(), b'x'*4_000_001):
            opener = Mock()
            opener.open.return_value = BytesIO(raw)
            with patch.object(live, 'build_opener', return_value=opener):
                with self.assertRaisesRegex(live.LiveSourceError, 'KMA_RESPONSE_INVALID'):
                    evaporation.fetch(evaporation.STATION_URL, {}, self.key)
            self.assertEqual(opener.open.call_count, 1)

    def test_retry_after_and_rate_limit_do_not_trigger_range_splitting(self):
        future = format_datetime(datetime.now(timezone.utc)+timedelta(minutes=1), usegmt=True)
        for status, header, expected in ((503, '60', 1), (503, future, 1),
                                          (429, '0', 2), (503, '0', 2), (503, 'invalid', 1)):
            with self.subTest(status=status, header=header):
                opener = Mock()
                opener.open.side_effect = [self.error(status, header) for _ in range(3)]
                with patch.object(live, 'build_opener', return_value=opener), \
                        patch.object(live.time, 'sleep'):
                    with self.assertRaisesRegex(live.LiveSourceError, 'KMA_UNAVAILABLE') as caught:
                        live.observed_forcing(
                            '421', self.start, self.start+timedelta(hours=7), self.key, chunk_hours=6)
                self.assertFalse(caught.exception.can_reduce_range)
                self.assertEqual(opener.open.call_count, expected)

    def test_retry_stops_when_lease_heartbeat_fails(self):
        heartbeat = Mock(side_effect=[None, ValueError('LIVE_LEASE_LOST')])
        opener = Mock()
        opener.open.side_effect = TimeoutError()
        with patch.object(live, 'build_opener', return_value=opener), \
                patch.object(live.time, 'sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'LIVE_LEASE_LOST'):
                evaporation.fetch(evaporation.STATION_URL, {}, self.key, heartbeat)
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()

    def test_smaller_successful_range_is_kept_for_remaining_observations(self):
        calls = []
        def fetch(station, start, end, key, heartbeat=None):
            calls.append((start, end))
            if end-start > timedelta(hours=1):
                raise live.LiveSourceError('KMA_UNAVAILABLE')
            rows, cursor = [], start
            while cursor <= end:
                rows.append(cursor.strftime('%Y%m%d%H%M')+' 421 0 0 0 0 0 0 20 0 0 0 0 0 60 1000 1010 10')
                cursor += timedelta(minutes=1)
            raw = ('#START7777\n# RN-15m RN-60m RN-12H RN-DAY\n'+'\n'.join(rows)+'\n#7777END').encode()
            return raw, {'sha256': live.hashlib.sha256(raw).hexdigest()}
        with patch.object(live, 'fetch_range', side_effect=fetch):
            value, sources = live.observed_forcing(
                '421', self.start, self.start+timedelta(hours=7), self.key, chunk_hours=6)
        self.assertEqual([end-start for start,end in calls[:3]],
                         [timedelta(hours=6), timedelta(hours=3), timedelta(hours=1)])
        self.assertTrue(all(end-start <= timedelta(hours=1) for start,end in calls[2:]))
        self.assertEqual(len(value['observations']), 420)
        self.assertEqual(sum(row['depthMm'] for row in value['observations']), 0)
        self.assertEqual(len(sources), len(calls)-2)

    def test_timeouts_are_bounded_and_leave_no_successful_source(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError()
        with patch.object(live, 'build_opener', return_value=opener), \
                patch.object(live.time, 'sleep') as sleep:
            with self.assertRaisesRegex(live.LiveSourceError, 'KMA_UNAVAILABLE'):
                evaporation.fetch(evaporation.STATION_URL, {}, self.key)
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once()
