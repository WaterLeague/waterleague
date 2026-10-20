"""가격 버전 복원·원가 검증과 물리 입력 비개입 검사."""
from copy import deepcopy
import hashlib
import json
from contextlib import closing
import unittest

from waterleague_sim.costing import game_prices, snapshot
from waterleague_sim.spatial.play_bundle import open_catalog
from waterleague_sim.engine.continuous import input_source


class GamePriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = open_catalog()
        with closing(cls.catalog.connection()) as db:
            cls.cell = [json.loads(db.execute("SELECT body FROM sites WHERE district_id='11200' AND json_extract(body,'$.allowedTypes') LIKE '%PERMEABLE_PAVEMENT%' LIMIT 1").fetchone()[0])]

    def test_metadata_keeps_previous_prices_and_rejects_unknown_or_rehashed_edits(self):
        new = self.catalog.metadata()
        previous = game_prices.apply(new, game_prices.catalog()['previousCostSourceSha256'])
        self.assertEqual(new['unitCosts']['PERMEABLE_PAVEMENT'], 123733)
        self.assertEqual(previous['unitCosts']['PERMEABLE_PAVEMENT'], 110000)
        six = game_prices.apply(new, '50f6e00757ecba3ed77a811b0fd9d03f72b800c0c47712093bf1adda99421036')
        self.assertNotIn('RAINWATER_CISTERN', six['unitCosts'])
        self.assertEqual(six['unitCosts']['PERMEABLE_PAVEMENT'], 110000)
        self.assertEqual(game_prices.apply(previous), new)
        for changed in (dict(new, costSourceSha256='0'*64), deepcopy(new)):
            changed['unitCosts']['PERMEABLE_PAVEMENT']=1
            with self.assertRaises(snapshot.CostEvidenceError): game_prices.apply(changed)
        with self.assertRaises(snapshot.CostEvidenceError): game_prices.apply(previous, '0'*64)
        self.assertEqual(game_prices.recorded_version(None,None), previous['costSourceSha256'])
        for raw, sha in [(None,'0'*64), ('{}',None), ('{}',hashlib.sha256(b'{}').hexdigest())]:
            with self.assertRaises(snapshot.CostEvidenceError): game_prices.recorded_version(raw,sha)

    def test_price_version_does_not_change_geometry_rainfall_or_swmm_input(self):
        cell = next(c for c in self.cell if 'PERMEABLE_PAVEMENT' in c['allowedTypes'])
        new = self.catalog.model(cell['id'],district=cell['districtId'])
        new['rainfall']={'start':'2022-08-08T09:00:00+00:00','end':'2022-08-08T09:02:00+00:00',
                        'depthsMm':[10,0],'stationId':'108','intervalSeconds':60}
        old = game_prices.apply(new,game_prices.catalog()['previousCostSourceSha256'])
        placement={'cellId':cell['id'],'facilityType':'PERMEABLE_PAVEMENT','areaM2':1}
        self.assertEqual(input_source(new,[placement],None),input_source(old,[placement],None))
        self.assertEqual(new['cells'],old['cells'])
