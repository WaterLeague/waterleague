"""실제 외부 호출 없이 공유 원장·동시 수집·시각 경계를 검사."""
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock
from waterleague_sim.ingestion import request_store as store, live, seoul_live

class RequestStoreTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        env=patch.dict(os.environ,{'EXTERNAL_REQUEST_STATE_DIR':directory.name});env.start();self.addCleanup(env.stop)

    def test_concurrent_consumers_download_once_and_preserve_acquisition_time(self):
        def fetch(): time.sleep(.1);return b'original'
        loader=Mock(side_effect=fetch)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:store.acquire('endpoint',{'station':'421'},'test',loader),range(8)))
        self.assertEqual(loader.call_count,1)
        self.assertEqual({r[0] for r in results},{b'original'})
        self.assertEqual(len({r[1]['fetchedAt'] for r in results}),1)
        self.assertEqual(sum(not r[1]['sharedResponse'] for r in results),1)

    def test_quota_reservation_is_atomic_and_survives_new_connection(self):
        def reserve(_):
            try: store.reserve('test',10,max_calls=3);return True
            except store.RequestBlocked:return False
        with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(reserve,range(12)))
        self.assertEqual(sum(results),3)
        with self.assertRaises(store.RequestBlocked):store.reserve('test',10,max_calls=3)

    def test_byte_budget_provider_isolation_and_kst_midnight_reset(self):
        before=datetime(2026,10,22,23,59,tzinfo=store.KST).timestamp()
        day=store.reserve('test',90,now=before,max_bytes=100)
        with self.assertRaises(store.RequestBlocked):store.reserve('test',11,now=before,max_bytes=100)
        store.settle('test',day,90,10)
        store.reserve('test',90,now=before,max_bytes=100)
        store.block('test',403,now=before)
        self.assertFalse(store.available('test',before))
        self.assertTrue(store.available('test',before+61))
        store.reserve('PUBLIC',10,now=before,provider='SEOUL_RAIN')

    def test_expired_or_corrupt_cache_is_never_returned_as_current(self):
        loader=Mock(return_value=b'first')
        store.acquire('endpoint',{},'test',loader,ttl=0)
        loader.side_effect=ValueError('source unavailable')
        with self.assertRaises(ValueError):store.acquire('endpoint',{},'test',loader)
        loader.side_effect=None;loader.return_value=b'fresh'
        store.acquire('endpoint',{},'test',loader)
        with store.database() as db:db.execute("UPDATE responses SET raw=X'00'")
        with self.assertRaises(store.RequestBlocked):store.acquire('endpoint',{},'test',loader)
        self.assertEqual(loader.call_count,3)

    def test_canonical_history_is_shared_but_observations_stop_at_requested_end(self):
        start=datetime(2026,10,14,12,17,tzinfo=store.KST);end=start+timedelta(minutes=5)
        first,last=live.canonical_range(start-timedelta(minutes=61),end)
        self.assertLessEqual(first,start-timedelta(minutes=61));self.assertGreaterEqual(last,end)
        calls=[]
        def retrieve(endpoint,parameters,key,heartbeat=None):
            calls.append(parameters)
            a,b=[datetime.strptime(parameters[k],'%Y%m%d%H%M').replace(tzinfo=store.KST) for k in ('tm1','tm2')]
            rows=[]
            while a<=b:
                rows.append(a.strftime('%Y%m%d%H%M')+' 421 0 0 0 0 0 0 20 0 0 0 0 0 60 1000 1010 10')
                a+=timedelta(minutes=1)
            return ('#START7777\n# RN-15m RN-60m RN-12H RN-DAY\n'+'\n'.join(rows)+'\n#7777END').encode()
        with patch.object(live,'read_response',side_effect=retrieve):
            result,sources=live.observed_forcing('421',start,end,'test',share_ranges=True)
            other,_=live.observed_forcing('421',start+timedelta(minutes=1),end,'test',share_ranges=True)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(result['observations']),5)
        self.assertEqual(len(other['observations']),4)
        self.assertEqual(datetime.fromisoformat(result['observations'][-1]['end']),end)
        self.assertLessEqual(datetime.fromisoformat(sources[0][1]['responseStart']),start)

    def test_live_canonical_window_never_requests_unpublished_future(self):
        now=datetime(2026,10,22,5,32,tzinfo=store.KST)
        first,last=live.canonical_range(now-timedelta(minutes=70),now-timedelta(minutes=2),now)
        self.assertEqual(last,now-timedelta(minutes=2))
        self.assertLessEqual(last-first,timedelta(days=1))

    def test_retry_after_can_cross_midnight_without_early_request(self):
        before=datetime(2026,10,22,23,59,tzinfo=store.KST).timestamp()
        store.block('test',429,180,now=before)
        self.assertFalse(store.available('test',before+61))
        with self.assertRaises(store.RequestBlocked):store.reserve('test',10,now=before+61)
        self.assertTrue(store.available('test',before+181))
