import unittest
from datetime import datetime,timedelta
from waterleague_sim.ingestion.kma import normalize
from waterleague_sim.ingestion.rainfall import RainfallQualityError
class KmaTests(unittest.TestCase):
 def source(self):
  start=datetime(2024,7,18,5)
  return '\n'.join(f'{start+timedelta(minutes=i):%Y%m%d%H%M} 108 0 0 0 0 0 0 25 1 1.5 6.0 10 {10+i/10:.1f} 90 1000 1000 24' for i in range(61))
 def test_cumulative_difference_and_crosscheck(self):
  rows,total=normalize(self.source());self.assertEqual(total,6);self.assertEqual(len(rows),60);self.assertEqual(rows[0].start.hour,20)
 def test_negative_and_missing_and_rolling_inconsistency(self):
  for change in [self.source().replace('10.1','9.9'),self.source().replace(' 6.0 ',' 6.2 '),self.source().replace('202407180530','202407180529')]:
   with self.assertRaises(RainfallQualityError):normalize(change)
 def test_midnight_rejected(self):
  with self.assertRaises(RainfallQualityError):normalize(self.source().replace('2024071805','2024071800'))
