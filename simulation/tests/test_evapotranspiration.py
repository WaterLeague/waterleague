"""FAO 공개 예제와 결측·시간 인과성 검사. 합성 기상은 시험 전용."""
import unittest
from datetime import datetime, timedelta, timezone

from waterleague_sim.engine.evapotranspiration import solar_hour, hourly
from waterleague_sim.ingestion.evaporation import KST, derive, append_evaporation, reusable_observation_hour, LiveSourceError
from waterleague_sim.ingestion.daily_evaporation import daily


class EvapotranspirationTests(unittest.TestCase):
    def test_fao56_example18_daily(self):
        result = daily(datetime(2001, 7, 6), 50.8, 100, 12.3, 21.5, 1.409, 10/3.6, 1001, 10, 22.07)
        self.assertAlmostEqual(result['referenceEtMmDay'], 3.88, delta=.02)
        self.assertAlmostEqual(result['extraterrestrialMjM2'], 41.09, delta=.02)
        with self.assertRaises(LiveSourceError):
            daily(datetime(2001, 7, 6), 50.8, 100, 12.3, 21.5, 1.409, 10/3.6, 1001, 10, -9)

    def test_fao56_example19_daytime(self):
        at = datetime(2001, 10, 1, 15, tzinfo=timezone(timedelta(hours=-1)))
        solar = solar_hour(at, 16+13/60, -16.25, 8)
        result = hourly(38, 52, 3.3, 1012, 2, 2.450, solar['clearSkyMjM2'], 2.450/solar['clearSkyMjM2'])
        self.assertAlmostEqual(solar['extraterrestrialMjM2'], 3.543, places=3)
        self.assertAlmostEqual(result['netRadiationMjM2'], 1.749, places=3)
        self.assertAlmostEqual(result['referenceEtMmHour'], .63, places=2)

    def fixture(self):
        start = datetime(2024, 7, 18, 0, tzinfo=KST)
        end = start+timedelta(hours=24)
        station = {'latitude': 37.57142, 'longitude': 126.9658, 'elevationM': 85.67, 'windHeightM': 7}
        radiation, weather = {}, {}
        for i in range(-36, 24):
            at = start+timedelta(hours=i)
            solar = solar_hour(at, station['latitude'], station['longitude'], station['elevationM'])
            radiation[at] = solar['clearSkyMjM2']*.6 if solar['clearSkyMjM2'] else None
        for i in range(-59, 24*60):
            weather[start+timedelta(minutes=i)] = {'temperatureC': 25, 'humidityPercent': 60,
                                                   'windSpeedMs': 2, 'pressureHpa': 1000}
        return start, end, station, radiation, weather

    def test_hour_boundary_night_and_required_observation(self):
        start, end, station, radiation, weather = self.fixture()
        result = derive(start, end, station, radiation, weather)
        self.assertEqual(len(result['ratesMmDay']), 1440)
        self.assertEqual(len(result['hours']), 24)
        self.assertEqual(result['hours'][0]['radiationBasis'], 'ASTRONOMICAL_NIGHT_ZERO')
        self.assertTrue(all(v >= 0 for v in result['ratesMmDay']))
        for hour in range(24):
            self.assertEqual(len(set(result['ratesMmDay'][hour*60:(hour+1)*60])), 1)
        noon = start+timedelta(hours=12)
        del weather[noon]
        with self.assertRaisesRegex(LiveSourceError, 'HOURLY_WEATHER_MISSING'):
            derive(start, end, station, radiation, weather)

    def test_missing_daylight_and_night_cloud_never_default_to_zero(self):
        start, end, station, radiation, weather = self.fixture()
        radiation[start+timedelta(hours=12)] = None
        with self.assertRaisesRegex(LiveSourceError, 'RADIATION_MISSING'):
            derive(start, end, station, radiation, weather)
        with self.assertRaisesRegex(LiveSourceError, 'NIGHT_CLOUD_MISSING'):
            derive(start, start+timedelta(hours=1), station, {start: None}, weather)

    def test_future_hour_cannot_change_earlier_minute_and_legacy_prefix_preserved(self):
        start, end, station, radiation, weather = self.fixture()
        before = derive(start, end, station, radiation, weather)
        radiation[start+timedelta(hours=12)] *= .8
        after = derive(start, end, station, radiation, weather)
        self.assertEqual(before['ratesMmDay'][:720], after['ratesMmDay'][:720])
        self.assertNotEqual(before['ratesMmDay'][720], after['ratesMmDay'][720])
        extension = before | {'sourceHashes': ['TEST_ONLY']}
        joined = append_evaporation(None, 10, 0, extension)
        self.assertEqual(joined['ratesMmDay'][:10], [0]*10)
        self.assertEqual(joined['legacyPrefixMinutes'], 10)
        second = append_evaporation(joined, len(joined['ratesMmDay']), 0, extension)
        self.assertEqual(second['ratesMmDay'][:1450], joined['ratesMmDay'])

    def test_reuse_stops_at_hour_boundary_and_retains_original_sources(self):
        start, _, station, radiation, weather = self.fixture()
        first = derive(start, start+timedelta(minutes=1), station, radiation, weather) | {'sourceHashes':['TEST_SOURCE'], 'sourceRequests':[]}
        prior = first
        for minute in range(1,60):
            begin=start+timedelta(minutes=minute)
            reused=reusable_observation_hour(prior,begin,begin+timedelta(minutes=1))
            self.assertIsNotNone(reused)
            self.assertEqual(reused['ratesMmDay'],first['ratesMmDay'])
            prior=append_evaporation(prior,minute,0,reused)
        self.assertEqual(len(prior['hours']),1)
        self.assertEqual(prior['sourceHashes'],['TEST_SOURCE'])
        self.assertEqual(len(prior['ratesMmDay']),60)
        self.assertEqual(prior['hours'][0]['appliesUntil'],(start+timedelta(hours=1)).isoformat())
        self.assertEqual(first['hours'][0]['appliesUntil'],(start+timedelta(minutes=1)).isoformat())
        self.assertIsNone(reusable_observation_hour(prior,start+timedelta(hours=1),start+timedelta(minutes=61)))
        self.assertIsNone(reusable_observation_hour(first,start+timedelta(minutes=3),start+timedelta(minutes=4)))
        self.assertIsNone(reusable_observation_hour(first|{'method':'ASSUMED_MODEL_CONSTANT'},start+timedelta(minutes=1),start+timedelta(minutes=2)))


if __name__ == '__main__':
    unittest.main()
