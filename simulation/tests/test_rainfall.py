from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import unittest
from waterleague_sim.ingestion.rainfall import RainInterval, RainfallQualityError, require_complete

class RainfallTests(unittest.TestCase):
    def setUp(self):
        self.start=datetime(2024,7,1,tzinfo=timezone.utc)
        self.rows=[RainInterval('test-station',self.start+timedelta(hours=i),self.start+timedelta(hours=i+1),Decimal(str(i)),'approved',f'test-{i}') for i in range(3)]
    def validate(self,rows):return require_complete(rows,self.start,self.start+timedelta(hours=3),3600,frozenset({'approved'}))
    def test_conserves_interval_depth(self):self.assertEqual(self.validate(self.rows),Decimal('3'))
    def test_missing_interval_is_not_zero_rain(self):
        with self.assertRaises(RainfallQualityError):self.validate([self.rows[0],self.rows[2]])
    def test_duplicate_and_overlap(self):
        with self.assertRaises(RainfallQualityError):self.validate([self.rows[0],self.rows[0],self.rows[2]])
    def test_incomplete_end(self):
        with self.assertRaises(RainfallQualityError):self.validate(self.rows[:2])
    def test_invalid_values(self):
        for value in [None,Decimal('NaN'),Decimal('Infinity'),Decimal('-1')]:
            with self.subTest(value=value),self.assertRaises(RainfallQualityError):self.validate([replace(self.rows[0],depth_mm=value),*self.rows[1:]])
    def test_quality_or_station_mismatch(self):
        for row in [replace(self.rows[0],quality='unknown'),replace(self.rows[0],station_id='different')]:
            with self.assertRaises(RainfallQualityError):self.validate([row,*self.rows[1:]])
    def test_timezone_required(self):
        with self.assertRaises(RainfallQualityError):self.validate([replace(self.rows[0],start=self.start.replace(tzinfo=None)),*self.rows[1:]])
    def test_accumulation_interval_cannot_be_relabelled(self):
        with self.assertRaises(RainfallQualityError):self.validate([replace(self.rows[0],end=self.start+timedelta(hours=24)),*self.rows[1:]])
if __name__=='__main__':unittest.main()
