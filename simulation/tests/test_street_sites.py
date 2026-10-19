"""도로 설계 구역의 제외·버전·공간 중첩·실제 과거 강우 점수 검사."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import sys
from shapely.geometry import Polygon, shape
from shapely.strtree import STRtree
from waterleague_sim import shared_model
from waterleague_sim.engine import continuous, initialization
from waterleague_sim.historical_antecedent import load as load_antecedent
from waterleague_sim.historical_evaporation import load as load_evaporation
from waterleague_sim.model_catalog import read_catalog
sys.path.insert(0, str(continuous.ROOT/'scripts'))
from prepare_street_sites import strips


class StreetSiteTests(unittest.TestCase):
    def test_strip_eligibility_and_explicit_sidewalks(self):
        road = {'id':'way/1:0','class':'residential','bridge':False,'motor':True,'widthM':7,'sidewalk':'unknown','coordinates':[[0,0],[50,0]]}
        result = list(strips(road, {}))
        self.assertEqual(len(result),3)
        self.assertTrue(all(role=='ROADWAY' and poly.area <=40 for _,role,_,poly in result))
        for changed,tags in [(road|{'bridge':True},{}),(road|{'class':'motorway'},{}),(road,{'access':'private'}),(road,{'surface':'gravel'})]:
            self.assertEqual(list(strips(changed,tags)),[])
        result = list(strips(road|{'sidewalk':'both'},{}))
        self.assertEqual(sum(role=='SIDEWALK' for _,role,_,_ in result),6)
        self.assertEqual({role for _,role,_,_ in strips(road|{'class':'footway','motor':False},{})},{'WALKWAY'})

    def test_additive_hashes_and_actual_district_spatial_nonoverlap(self):
        district='2410520'
        cells=shared_model.candidates(district,10)
        previous=shared_model.candidates(district,9)
        self.assertFalse(cells.keys() & previous.keys())
        self.assertEqual(len(cells),shared_model.site_catalog(10)[district]['count'])
        city=json.loads((continuous.ROOT/'frontend/public/data/seoul-v1/city.json').read_bytes())
        boundary=shape({'type':'MultiPolygon','coordinates':next(d for d in city['districts'] if d['id']==district)['polygons']})
        geometries=[Polygon(c['coordinates']) for c in cells.values()]
        tree=STRtree(geometries)
        old=[Polygon(c['coordinates']) for c in previous.values()];old_tree=STRtree(old)
        roles=set()
        for index,(cell,poly) in enumerate(zip(cells.values(),geometries)):
            self.assertTrue(boundary.covers(poly)); self.assertTrue(poly.is_valid)
            self.assertAlmostEqual(poly.area,cell['areaM2'],places=6)
            self.assertGreater(cell['maxAreaM2'],0); self.assertLessEqual(cell['maxAreaM2'],poly.area)
            self.assertEqual(cell['allowedTypes'],['PERMEABLE_PAVEMENT'])
            self.assertEqual(cell['areaLimitBasis'],'PUBLIC_CENTERLINE_DESIGN_STRIP')
            self.assertEqual(cell['inflowPolicy'],'DIRECT_RAINFALL_ONLY')
            roles.add(cell['physicalInputs']['streetPlacement']['role'])
            for j in tree.query(poly,predicate='intersects'):
                if int(j)>index:self.assertLessEqual(poly.intersection(geometries[int(j)]).area,1e-6)
            for j in old_tree.query(poly,predicate='intersects'):
                self.assertLessEqual(poly.intersection(old[int(j)]).area,1e-6)
        self.assertEqual(roles,{'ROADWAY','SIDEWALK','WALKWAY'})
        for version in (9,10):
            cell=next(iter(shared_model.candidates(district,version).values()))
            model,_,_=shared_model.resolve({'district_id':district,'cell_id':cell['id'],'model_hash':shared_model.site_catalog(version)[district]['sha256']})
            self.assertEqual(model['cells'][0],cell)

    @unittest.skipUnless(continuous.library_path().exists(),'EPA 연속 엔진 필요')
    def test_observed_rain_road_and_walkway_water_balance_and_replay(self):
        district='2410520'
        records=read_catalog(continuous.ROOT/'data/models')
        model_hash, observed=next((key,json.loads(raw)) for key,raw in records.items()
            if json.loads(raw).get('mapId')=='seoul-osm-v1-2410520'
            and json.loads(raw).get('rainfall',{}).get('start','').startswith('2022-08-08'))
        for role in ('ROADWAY','WALKWAY'):
            cell=next(c for c in shared_model.candidates(district,10).values()
                if c['physicalInputs']['streetPlacement']['role']==role and c['maxAreaM2']>=10)
            model,_,_=shared_model.resolve({'district_id':district,'cell_id':cell['id'],'model_hash':shared_model.site_catalog(10)[district]['sha256']})
            model['rainfall']=copy.deepcopy(observed['rainfall'])
            placement={'cellId':cell['id'],'facilityType':'PERMEABLE_PAVEMENT','areaM2':10}
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                evaporation=load_evaporation(model_hash,observed,root/'sources')
                antecedent=load_antecedent(model_hash,root/'sources')
                expanded,pet=initialization.prepend(model,evaporation,antecedent)
                result=continuous.experiment(expanded,placement,root/'first',pet)
                replay=continuous.experiment(expanded,placement,root/'second',pet)
                final=result['strategy']['final']
                self.assertGreater(final['lidInfiltrationM3'],0)
                self.assertGreater(result['contribution'][-1]['cumulativeM3'],0)
                self.assertAlmostEqual(final['lidInflowM3'],sum(model['rainfall']['depthsMm'])*10/1000,places=6)
                self.assertLess(abs(final['balanceResidualM3']),.01*(final['precipitationM3']+final['initialStorageM3']))
                self.assertEqual(result['strategy'],replay['strategy'])
                self.assertTrue(result['initialization']['scoreExcludesWarmup'])
                print(json.dumps({'role':role,'site':cell['id'],'areaM2':10,'rainMm':sum(model['rainfall']['depthsMm']),
                    'scoreM3':result['contribution'][-1]['cumulativeM3'],'infiltrationM3':final['lidInfiltrationM3'],'balanceResidualM3':final['balanceResidualM3'],'exactReplay':True}),flush=True)


if __name__=='__main__':unittest.main()
