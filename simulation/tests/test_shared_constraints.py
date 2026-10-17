"""공개 도형의 면적 상한과 설치 당시 버전 보존 검사."""
import gzip,json,sys,unittest
from pathlib import Path
from waterleague_sim.shared_model import catalog,candidates,resolve,site_catalog,with_observed_forcing
from waterleague_sim.engine.continuous import ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_shared_site_constraints import constrain

class SharedConstraintTests(unittest.TestCase):
    def test_area_constraint_is_geometry_not_arbitrary_ratio(self):
        cell={'coordinates':[[0,0],[10,0],[10,10],[0,10],[0,0]],'areaM2':100,'maxAreaM2':60}
        self.assertEqual(constrain(cell)['maxAreaM2'],100)
        self.assertEqual(cell['maxAreaM2'],60)
        with self.assertRaises(ValueError):constrain(cell|{'areaM2':110})
    def test_all_districts_preserve_candidates_and_old_installations(self):
        districts,sites,_=catalog()
        for d in districts:
            current=candidates(d);old=candidates(d,1)
            self.assertEqual(set(old)-set(current),set())
            self.assertEqual(len(current),sites[d]['count'])
            for c in current.values():
                self.assertGreater(c['maxAreaM2'],0)
                self.assertLessEqual(c['maxAreaM2'],c['areaM2'])
                self.assertLess(c['areaM2']-c['maxAreaM2'],.011)
            first=next(iter(old))
            prior,_,_=resolve({'district_id':d,'cell_id':first,'model_hash':site_catalog(1)[d]['sha256']})
            new,_,_=resolve({'district_id':d,'cell_id':first,'model_hash':sites[d]['sha256']})
            self.assertEqual(prior['cells'][0]['maxAreaM2'],old[first]['maxAreaM2'])
            self.assertEqual(new['sharedSiteSource']['inflowPolicy'],'DIRECT_RAINFALL_ONLY')

    def test_cost_revision_preserves_geometry_and_historical_price(self):
        d='2410520';cell='G1'
        old,_,_=resolve({'district_id':d,'cell_id':cell,'model_hash':site_catalog(2)[d]['sha256']})
        new,_,_=resolve({'district_id':d,'cell_id':cell,'model_hash':site_catalog(3)[d]['sha256']})
        self.assertEqual(new['cells'],old['cells'])
        self.assertEqual(new['hydrology'],old['hydrology'])
        self.assertEqual(old['unitCosts']['GREEN_ROOF'],260000)
        self.assertEqual(new['unitCosts']['GREEN_ROOF'],350000)
        self.assertEqual(new['costModel']['facilities']['GREEN_ROOF']['includes'],['구조안전진단','설계','공사'])

    def test_budget_policy_is_frozen_without_changing_old_candidate_input(self):
        policy=json.loads((ROOT/'backend/src/main/resources/budget/seoul-2026.json').read_text())
        installation={'district_id':'2410520','cell_id':'G1','model_hash':site_catalog(3)['2410520']['sha256']}
        old,_,_=resolve(installation)
        new,_,_=resolve(installation|{'budget_policy':json.dumps(policy)})
        self.assertEqual(old['budget'],2000000000)
        self.assertEqual(new['budget'],80000000)
        self.assertEqual(new['budgetPolicy'],policy)
        self.assertEqual(new['cells'],old['cells'])
        self.assertEqual(new['hydrology'],old['hydrology'])
        with self.assertRaises(ValueError):
            resolve(installation|{'budget_policy':policy|{'districtLimitKrw':80000001}})

    def test_effective_forcing_notes_preserve_physical_inputs_and_original_model(self):
        from waterleague_sim.engine.continuous import input_source
        model,_,_=resolve({'district_id':'2410520','cell_id':'G1','model_hash':site_catalog(3)['2410520']['sha256']})
        self.assertFalse(any('2024' in a or '유출 전량' in a for a in model['assumptions']))
        model['rainfall']={'start':'2026-10-17T00:00:00+09:00','end':'2026-10-17T00:02:00+09:00','intervalSeconds':60,'depthsMm':[0,0]}
        evap={'method':'SYNTHETIC_TEST_ONLY','sourceHashes':['test'],'ratesMmDay':[0,1]}
        original=json.dumps(model,sort_keys=True)
        bound=with_observed_forcing(model,evap)
        self.assertEqual(json.dumps(model,sort_keys=True),original)
        self.assertEqual(model['hydrology'],bound['hydrology'])
        self.assertEqual(input_source(model,[],evap),input_source(bound,[],evap))
        self.assertFalse(any('증발 0 가정' in a for a in bound['assumptions']))
        self.assertTrue(any('경사 1%' in a for a in bound['assumptions']))
        with self.assertRaises(ValueError):with_observed_forcing(model,{})
