"""인접 실관측 보강의 시간 경계·원 관측 보존·출처·실패 경계 검사."""
import hashlib
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

from waterleague_sim.ingestion import live, seoul_live
from waterleague_sim.ingestion.rainfall import RainfallQualityError


class SeoulLiveTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 16, 15, 0, tzinfo=live.KST)
        self.end = self.start + timedelta(minutes=10)
        self.rain = {'stationId': '415', 'observations': [], 'sourceHashes': ['a'*64],
                     'qualityPolicy': 'ORIGINAL', 'evidence': 'ORIGINAL'}
        self.row = {'rf_cd': 2102, 'rf_nm': '흑석P', 'gu_nm': '동작구',
                    'data_clct_tm': '2026-10-16 15:09', 'rn_10m': '2.5'}

    def fetcher(self, rows):
        raw = json.dumps({'DATA': rows}, ensure_ascii=False).encode()
        self.raw = raw
        return Mock(return_value=(raw, {'sha256': hashlib.sha256(raw).hexdigest()}))

    def test_positive_total_preserved_and_nearest_station_fixed_before_values(self):
        fetch = self.fetcher([self.row])
        result, sources = seoul_live.supplement(self.rain, self.start, self.end, fetch)
        fetch.assert_called_once_with('2102', heartbeat=None)
        self.assertEqual(sum(v['depthMm'] for v in result['observations']), 2.5)
        self.assertTrue(all(v['method'] == 'SEOUL_NEAREST_10M_MEAN_ASSUMPTION' for v in result['observations']))
        self.assertEqual(result['supplement']['minutes'], 10)
        self.assertEqual(result['supplement']['fraction'], 1)
        self.assertEqual(result['supplement']['binding']['distanceM'], 1594.028)
        self.assertEqual(sources[0][0], self.raw)
        self.assertEqual({meta['sha256'] for _, meta in sources}, set(result['sourceHashes'])-{'a'*64})

    def test_valid_primary_minutes_never_replaced_or_subtracted_from_other_station(self):
        saved = {'end': (self.start+timedelta(minutes=1)).isoformat(), 'depthMm': 3,
                 'method': 'DAILY_DIFFERENCE', 'weather': {'temperatureC': 18}}
        self.rain['observations'] = [saved]
        result, _ = seoul_live.supplement(self.rain, self.start, self.end, self.fetcher([self.row]))
        self.assertEqual(result['observations'][0], saved)
        self.assertEqual(result['supplement']['minutes'], 9)
        self.assertEqual(result['supplement']['intervals'][0]['appliedDepthMm'], 2.25)
        self.assertEqual(sum(v['depthMm'] for v in result['observations']), 5.25)

    def test_complete_primary_skips_network_and_remains_identical(self):
        self.rain['observations'] = [{'end': (self.start+timedelta(minutes=i)).isoformat(), 'depthMm': 0}
                                     for i in range(1, 11)]
        fetch = Mock(side_effect=AssertionError('보조 조회 금지'))
        result, sources = seoul_live.supplement(self.rain, self.start, self.end, fetch)
        self.assertIs(result, self.rain)
        self.assertEqual(sources, [])
        fetch.assert_not_called()

    def test_midnight_and_observed_zero_are_distinct_from_missing(self):
        start = datetime(2026, 10, 16, 23, 50, tzinfo=live.KST)
        row = self.row | {'data_clct_tm': '2026-10-16 23:59', 'rn_10m': '0'}
        result, _ = seoul_live.supplement(self.rain, start, start+timedelta(minutes=10), self.fetcher([row]))
        self.assertEqual(len(result['observations']), 10)
        self.assertTrue(all(v['method'] == 'SEOUL_NEAREST_10M_ZERO_ASSUMPTION' and v['depthMm'] == 0
                            for v in result['observations']))
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_REQUIRED_INTERVAL_MISSING'):
            seoul_live.supplement(self.rain, self.start, self.end, self.fetcher([row]))

    def test_future_partial_ten_minutes_cannot_initialize_past_state(self):
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_REQUIRED_INTERVAL_MISSING'):
            seoul_live.supplement(self.rain, self.start, self.end-timedelta(minutes=1), self.fetcher([self.row]))

    def test_bad_source_values_identity_time_duplicates_and_hash_fail_closed(self):
        for field, value in [('rn_10m', '-99.9'), ('rn_10m', 'NaN'), ('rn_10m', 'Infinity'),
                             ('rf_nm', '다른 관측소'), ('gu_nm', '용산구'),
                             ('data_clct_tm', '2026-10-16 15:08')]:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_SOURCE_INVALID'):
                seoul_live.supplement(self.rain, self.start, self.end, self.fetcher([self.row | {field: value}]))
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_SOURCE_INVALID'):
            seoul_live.supplement(self.rain, self.start, self.end, self.fetcher([self.row, self.row]))
        fetch = self.fetcher([self.row])
        fetch.return_value = (self.raw, {'sha256': 'b'*64})
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_SOURCE_HASH_INVALID'):
            seoul_live.supplement(self.rain, self.start, self.end, fetch)

    def test_partial_code_search_uses_only_exact_station_id(self):
        foreign = self.row | {'rf_cd': 12102, 'rf_nm': '다른 관측소', 'rn_10m': '20'}
        result, _ = seoul_live.supplement(self.rain, self.start, self.end, self.fetcher([foreign, self.row]))
        self.assertEqual(sum(v['depthMm'] for v in result['observations']), 2.5)
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_REQUIRED_INTERVAL_MISSING'):
            seoul_live.supplement(self.rain, self.start, self.end, self.fetcher([foreign]))

    def test_unknown_station_or_older_location_period_does_not_select_another(self):
        fetch = Mock(side_effect=AssertionError('보조 조회 금지'))
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_BINDING_UNAVAILABLE'):
            seoul_live.supplement(self.rain | {'stationId': '99999'}, self.start, self.end, fetch)
        with self.assertRaisesRegex(RainfallQualityError, 'SEOUL_RAIN_LOCATION_PERIOD_UNSUPPORTED'):
            seoul_live.supplement(self.rain, self.start-timedelta(days=30), self.end-timedelta(days=30), fetch)
        fetch.assert_not_called()
