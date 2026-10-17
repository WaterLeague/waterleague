"""공개 도형의 면적 상한과 설치 당시 버전 보존 검사."""
import gzip,json,sys,unittest
from pathlib import Path
from waterleague_sim.shared_model import catalog,candidates,resolve,site_catalog
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
