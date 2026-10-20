"""선행 기상 입력의 시간 인과성과 구간 총량 보존 검사."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from waterleague_sim.ingestion import antecedent, live
from waterleague_sim.ingestion.hourly_rainfall import observed

class AntecedentSourcesTests(unittest.TestCase):
    def test_only_previous_complete_days_supply_initialization_weather(self):
        start=datetime(2022,8,1,18,tzinfo=live.KST);end=start+timedelta(days=7)
        calls=[]
        def daily(before, after, key, fetch):
            calls.append((before,after))
            return {'ratesMmDay':[3]*1440,'sourceHashes':['test-only'],'sourceRequests':[],
                    'assumptions':[]},[]
        with patch('waterleague_sim.ingestion.antecedent.observed_daily',side_effect=daily):
            value,_=antecedent.weather(start,end,'test-only',lambda *a:None)
        self.assertEqual(len(value['ratesMmDay']),10080)
        self.assertEqual(len(value['segments']),8)
        for (before,after),segment in zip(calls,value['segments'],strict=True):
            self.assertLessEqual(after,datetime.fromisoformat(segment['start']))
            self.assertEqual(after-before,timedelta(days=1))
            self.assertEqual(segment['timePolicy'],'PREVIOUS_COMPLETED_DAY_HELD_OVER_NEXT_DAY')

    def test_hourly_fallback_is_same_station_and_no_future_partial_hour(self):
        start=datetime(2022,8,1,18,tzinfo=live.KST)
        with self.assertRaises(live.LiveSourceError): observed('404',start,start+timedelta(hours=1),'test-only')
        with self.assertRaises(live.LiveSourceError): observed('108',start,start+timedelta(minutes=59),'test-only')

    def test_network_timeout_splits_request_without_filling_missing_data(self):
        start=datetime(2022,8,1,18,tzinfo=live.KST);end=start+timedelta(hours=1)
        calls=[]
        def fetch(station,first,last,key,heartbeat=None):
            calls.append((first,last))
            if (last-first)>timedelta(hours=1): raise live.LiveSourceError('KMA_UNAVAILABLE')
            raise live.LiveSourceError('KMA_ACCESS_UNAVAILABLE')
        with patch('waterleague_sim.ingestion.live.fetch_range',side_effect=fetch):
            with self.assertRaisesRegex(live.LiveSourceError,'KMA_ACCESS_UNAVAILABLE'):
                live.observed_forcing('108',start,end,'test-only',chunk_hours=6)
        self.assertGreater(len(calls),1)
        self.assertLessEqual((calls[-1][1]-calls[-1][0]).total_seconds(),3600)
