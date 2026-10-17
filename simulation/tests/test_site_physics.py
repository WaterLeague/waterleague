"""공개자료 파생 입력과 EPA 수치 경로 검사. 합성 경사는 수학 시험 전용."""
import copy,json,math,sys,tempfile,unittest
from pathlib import Path
from waterleague_sim.shared_model import catalog,candidates,resolve,site_catalog
from waterleague_sim.engine.continuous import ROOT,input_source,experiment
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_site_physics import geometry_inputs,horn

class SitePhysicsTests(unittest.TestCase):
    def test_shape_aspect_ratio_and_horn_gradient(self):
        c={'coordinates':[[0,0],[20,0],[20,5],[0,5],[0,0]],'areaM2':100,'sourceIds':['TEST_ONLY']}
        p=geometry_inputs(c)
        self.assertEqual(p['runoffWidthM'],5)
        self.assertEqual(p['flowLengthM'],20)
        self.assertNotEqual(p['runoffWidthM'],math.sqrt(c['areaM2']))
        self.assertAlmostEqual(horn([0,1,2,2,3,4,4,5,6],10,10),math.sqrt(.1**2+.2**2)*100)
        self.assertIsNone(horn([0]*8+[-9999],10,10))
        with self.assertRaises(ValueError):geometry_inputs(c|{'areaM2':101})

    def test_steep_small_surface_conserves_water_at_short_live_window(self):
        from datetime import datetime,timedelta,timezone
        m,_,_=resolve({'district_id':'2419953','cell_id':'G1','model_hash':site_catalog(4)['2419953']['sha256']})
        start=datetime(2026,10,18,tzinfo=timezone.utc)
        m['rainfall']={'start':start.isoformat(),'end':(start+timedelta(minutes=7)).isoformat(),'intervalSeconds':60,'depthsMm':[.3]*7,'evidence':'SYNTHETIC_TEST_ONLY'}
        evap={'method':'SYNTHETIC_TEST_ONLY','sourceHashes':['test'],'ratesMmDay':[2]*7}
        with tempfile.TemporaryDirectory() as temp:
            r=experiment(m,{'cellId':'G1','facilityType':'RAIN_GARDEN','areaM2':25},Path(temp),evap)
            final=r['baseline']['final']
            self.assertLess(abs(final['balanceResidualM3'])/final['precipitationM3'],.002)

    def test_actual_source_coverage_and_old_snapshots(self):
        coverage={'geometry':0,'terrainSlope':0,'soil':0,'material':0}
        for d in catalog()[0]:
            old=candidates(d,3);new=candidates(d,4)
            self.assertEqual(set(old),set(new))
            for key,c in new.items():
                self.assertEqual({k:v for k,v in c.items() if k!='physicalInputs'},old[key])
                p=c['physicalInputs'];coverage['geometry']+=1
                if p['slopeMethod']=='NGII_2025_90M_HORN_TERRAIN_PROXY':
                    self.assertEqual(c['kind'],'GROUND');coverage['terrainSlope']+=1
                if 'conductivityMmH' in p:coverage['soil']+=1
                if 'nImpervious' in p:coverage['material']+=1
        registered=json.loads((ROOT/'data/manifests/shared-sites-v4.json').read_text())['coverage']
        self.assertEqual(coverage,{k:registered[k] for k in coverage})

    def test_actual_observed_event_changes_engine_inputs_and_outputs(self):
        found=None
        for d in catalog()[0]:
            found=next(((d,c) for c in candidates(d).values() if c['kind']=='GROUND' and c['physicalInputs']['slopeMethod'].startswith('NGII') and 'conductivityMmH' in c['physicalInputs']),None)
            if found:break
        self.assertIsNotNone(found)
        d,c=found
        old,_,_=resolve({'district_id':d,'cell_id':c['id'],'model_hash':site_catalog(3)[d]['sha256']})
        model,_,_=resolve({'district_id':d,'cell_id':c['id'],'model_hash':site_catalog(4)[d]['sha256']})
        events=json.loads((ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())
        h=next(r['modelHash'] for r in events['events'][0]['models'] if r['districtId']==d)
        observed=json.loads(catalog()[2][h]);model['rainfall']=observed['rainfall'];old['rainfall']=observed['rainfall']
        from waterleague_sim.historical_evaporation import load
        with tempfile.TemporaryDirectory() as temp:
            evap=load(h,observed,Path(temp))
            placement={'cellId':c['id'],'facilityType':'PERMEABLE_PAVEMENT','areaM2':c['maxAreaM2']}
            source=input_source(model,[placement],evap)
            p=c['physicalInputs']
            line=source.split('[SUBCATCHMENTS]\n')[1].splitlines()[0].split()
            self.assertEqual(float(line[5]),p['runoffWidthM']);self.assertEqual(float(line[6]),p['slopePercent'])
            line=source.split('[INFILTRATION]\n')[1].splitlines()[0].split()
            self.assertEqual(float(line[2]),p['conductivityMmH'])
            a=experiment(old,placement,Path(temp)/'old',evap);b=experiment(model,placement,Path(temp)/'new',evap)
            self.assertNotEqual(a['strategy']['final']['infiltrationM3'],b['strategy']['final']['infiltrationM3'])
            self.assertLess(abs(b['strategy']['runoffContinuityPercent']),1)
            self.assertTrue(all(v['infiltrationM3']>=0 for v in b['strategy']['samples']))
            invalid=copy.deepcopy(model);invalid['cells'][0]['physicalInputs']['slopePercent']=float('nan')
            with self.assertRaises(ValueError):input_source(invalid,[placement],evap)
