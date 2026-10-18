"""풍향·SI 계수·무풍/건조·기상 시계와 네이티브 수지 검사."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.surface_wind import WindSeries, POLICY, aws_rows, require_wind_clock
from waterleague_sim.reference.flood_cases import mesh


def numerical(model, *, speeds=(5., 5.), directions=(270., 270.)):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    model.update(schemaVersion=2, startUtc=start.isoformat(), durationSeconds=60*len(speeds))
    return {'schemaVersion': 1, 'policyVersion': POLICY, 'type': 'NUMERICAL_TEST_SERIES',
        'integrationPolicy': 'ANUGA_EXPLICIT_DIAGNOSTIC_V1',
        'measurementHeightM': 10., 'heightCorrection': 'POWER_LAW_ONE_SEVENTH_UNCALIBRATED',
        'airDensityKgM3': 1.2, 'waterDensityKgM3': 1000.,
        'dragLaw': 'CONSTANT_NUMERICAL_ONLY', 'constantDragCoefficient': .001,
        'vectorBasis': 'LOCAL_TRUE_EAST_NORTH_DIAGNOSTIC', 'evidence': '합성 해석 검사용 균일 바람',
        'densityEvidence': '해석 검사를 위해 명시한 SI 밀도',
        'intervals': [{'startUtc': (start+timedelta(seconds=60*i)).isoformat(),
                       'endUtc': (start+timedelta(seconds=60*(i+1))).isoformat(),
                       'speedMs': speed, 'fromDegrees': direction}
                      for i, (speed, direction) in enumerate(zip(speeds, directions))]}


def archived():
    name = 'seoul-20220808-fao56-v1.json'
    return {'schemaVersion': 1, 'policyVersion': POLICY, 'type': 'ARCHIVED_KMA_AWS',
        'integrationPolicy': 'FROZEN_DRAG_EXACT_RELATIVE_V1',
        'reference': {'file': name, 'sha256': hashlib.sha256((ROOT/'data/derived/evaporation'/name).read_bytes()).hexdigest()},
        'heightCorrection': 'POWER_LAW_ONE_SEVENTH_UNCALIBRATED',
        'airDensityKgM3': 1.29, 'waterDensityKgM3': 1000., 'dragLaw': 'GARRATT_HEC_6_6',
        'vectorBasis': 'LOCAL_TRUE_EAST_NORTH_DIAGNOSTIC',
        'evidence': '실제 서울 108 기상을 합성 지표에 균일 배정; 서울 침수 예측 아님',
        'densityEvidence': 'HEC-RAS 6.6의 공기밀도 근사와 담수 1000kg/m³ 고정 가정; 현장 실측 아님'}


def uniform(*, nx=2, depth=1., step=.5):
    model = mesh(nx, nx, 100, 100, water=lambda x, z: x*0+depth)
    model['maxStepSeconds'] = step
    model['boundaryConditions'] = {k: {'type': 'TRANSMISSIVE'} for k in model['boundaryConditions']}
    return model


def run(model, directory, *, steps=None):
    with EngineProcess('surface', model, directory) as session:
        for dt in steps or [model['durationSeconds']]:
            session.call('advance', dt)
        return session.call('finish')


class WindInputTests(unittest.TestCase):
    def test_cardinal_from_direction_and_seven_meter_height(self):
        model = uniform()
        spec = numerical(model, speeds=(5.,)*4, directions=(0.,90.,180.,270.))
        spec['measurementHeightM'] = 7.
        s = WindSeries(spec, model)
        expected = [(0,-1),(-1,0),(0,1),(1,0)]
        speed = 5*(10/7)**(1/7)
        for i, vector in enumerate(expected):
            for actual, sign in zip(s.vector(60*i,60),vector):
                self.assertAlmostEqual(actual,sign*speed,places=12)
        with self.assertRaisesRegex(FloodModelError,'STRADDLED'):
            s.vector(59,2)
        with self.assertRaisesRegex(FloodModelError,'EXCEEDED'):
            s.vector(240,1)

    def test_actual_archive_uses_completed_minute_and_original_height(self):
        model = uniform()
        model.update(schemaVersion=2,startUtc='2022-08-08T09:00:00Z',durationSeconds=3600)
        s = WindSeries(archived(),model)
        self.assertEqual(s.summary['measuredHeightM'],7.)
        self.assertEqual(s.summary['intervalCount'],60)
        self.assertEqual(len(s.files)>3,True)
        self.assertEqual(s.summary['timePolicy'],'COMPLETED_ONE_MINUTE_MEAN_HELD_OVER_NEXT_MINUTE')
        self.assertTrue(all(abs(x)<15 for x in s.vector(0,60)))
        broken = deepcopy(model) | {'durationSeconds':21600}
        with self.assertRaisesRegex(FloodModelError,'COVERAGE_INCOMPLETE'):
            WindSeries(archived(),broken)
        spec = archived()
        spec['reference']['sha256']='0'*64
        with self.assertRaisesRegex(FloodModelError,'HASH_MISMATCH'):
            WindSeries(spec,model)

    def test_invalid_density_gap_calm_and_clock_rejected(self):
        model = uniform()
        spec=numerical(model)
        for key,value in [('airDensityKgM3',.0012),('measurementHeightM',None),('vectorBasis','GRID_NORTH_GUESSED')]:
            with self.assertRaises(FloodModelError):WindSeries(spec|{key:value},model)
        gap=deepcopy(spec);gap['intervals'][1]['startUtc']='2020-01-01T00:01:01Z'
        with self.assertRaisesRegex(FloodModelError,'GAP_OR_OVERLAP'):WindSeries(gap,model)
        bad=deepcopy(spec);bad['intervals'][0]['fromDegrees']=360
        with self.assertRaisesRegex(FloodModelError,'DIRECTION'):WindSeries(bad,model)
        with self.assertRaisesRegex(FloodModelError,'SOURCE_KIND'):
            WindSeries(spec,model|{'evidence':'SITE_VALIDATED'})
        model['wind']=spec
        with self.assertRaisesRegex(FloodModelError,'RAIN_CLOCK'):
            require_wind_clock(model,duration=120,rainfall={'startUtc':'2020-01-01T00:00:01Z','endUtc':'2020-01-01T00:02:01Z'})
        raw=(ROOT/'data/raw/kma-disaster-pet-aa549fa6b7d01d1ebcbbd98f.txt').read_bytes()
        with self.assertRaisesRegex(FloodModelError,'CALM_CONFLICT'):
            aws_rows(raw.replace(b'173.1    3.3',b'360.0    3.3',1))


class WindEngineTests(unittest.TestCase):
    def test_analytical_uniform_relative_wind_time_and_grid_convergence(self):
        results=[]
        exact=5-5/(1+.001*1.2/1000*5*120)
        with tempfile.TemporaryDirectory() as tmp:
            for name,step,nx in [('coarse',1.,2),('fine',.5,2),('grid',.5,4),('replay',.5,2)]:
                model=uniform(nx=nx,step=step);model['wind']=numerical(model)
                result=run(model,Path(tmp)/name)
                velocity=sum(result['final']['velocityXMps'])/len(result['final']['velocityXMps'])
                self.assertEqual(result['numericalStatus'],'PASSED')
                self.assertAlmostEqual(result['final']['storageM3'],10000,places=8)
                self.assertLess(abs(result['final']['balanceResidualM3']),1e-7)
                self.assertEqual(result['wind']['waterVolumeAddedM3'],0)
                self.assertLess(abs(velocity-exact),3e-8)
                results.append((velocity,result))
            self.assertLess(abs(results[1][0]-exact),abs(results[0][0]-exact))
            self.assertAlmostEqual(results[1][0],results[2][0],places=11)
            self.assertEqual(results[1][1]['final'],results[3][1]['final'])
            self.assertEqual(results[1][1]['wind'],results[3][1]['wind'])

    def test_calm_and_dry_no_water_or_momentum_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name,depth,speed,direction in [('dry',0.,5.,270.),('calm',1.,0.,360.)]:
                model=uniform(depth=depth);model['wind']=numerical(model,speeds=(speed,),directions=(direction,))
                result=run(model,Path(tmp)/name)
                self.assertEqual(result['final']['sourceNetInflowM3'],0)
                self.assertEqual(result['wind']['impulseXKgMps'],0)
                self.assertEqual(result['wind']['impulseYKgMps'],0)
                self.assertLess(max(abs(x) for x in result['final']['velocityXMps']),1e-12)

    def test_observation_knots_long_steps_and_projected_basis(self):
        model=uniform();model['wind']=numerical(model,speeds=(5.,5.),directions=(270.,90.))
        with tempfile.TemporaryDirectory() as tmp:
            a=run(model,Path(tmp)/'long')
            b=run(model,Path(tmp)/'split',steps=[60,60])
            self.assertEqual(a['final'],b['final'])
            self.assertEqual(a['wind'],b['wind'])
            from pyproj import Transformer
            origin=Transformer.from_crs('EPSG:4326','EPSG:5186',always_xy=True).transform(127.,37.5)
            model['verticesM']=[[x+origin[0],y+origin[1]] for x,y in model['verticesM']]
            model['coordinateSystem']='EPSG:5186'
            model['wind']['vectorBasis']='PROJECTED_TRUE_NORTH_WGS84'
            projected=run(model,Path(tmp)/'projected')
            self.assertLess(projected['wind']['basisDistanceConvergenceError'],1e-6)
            self.assertEqual(projected['numericalStatus'],'PASSED')

    def test_combined_network_exchange_and_observed_wind_ledger(self):
        from test_observed_surface_rainfall import observed_coupled
        from waterleague_sim.engine.coupled_flood import run_coupled
        model=observed_coupled()
        surface=model['surface']
        surface.update(schemaVersion=2,startUtc='2022-08-08T09:00:00Z',durationSeconds=120,wind=archived())
        surface['initialDepthM']=[.01]*len(surface['triangles'])
        with tempfile.TemporaryDirectory() as tmp:
            result=run_coupled(model,Path(tmp)/'coupled')
        self.assertEqual(result['numericalStatus'],'PASSED')
        self.assertTrue(result['surfaceWind']['complete'])
        self.assertEqual(result['surfaceWind']['waterVolumeAddedM3'],0)
        self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']),1e-8)

    def test_exact_relative_drag_shallow_water_no_overshoot(self):
        model=uniform(depth=.00002,step=1)
        model['wind']=numerical(model,speeds=(20.,),directions=(270.,))
        model['wind']['integrationPolicy']='FROZEN_DRAG_EXACT_RELATIVE_V1'
        exact=20-20/(1+.001*1.2/1000*20*60/.00002)
        with tempfile.TemporaryDirectory() as tmp:
            result=run(model,Path(tmp)/'shallow')
        self.assertLess(max(abs(v-exact) for v in result['final']['velocityXMps']),1e-9)
        self.assertGreater(result['wind']['maximumExplicitRelaxation'],.25)
        self.assertLessEqual(max(result['final']['velocityXMps']),20)
        self.assertLess(abs(result['final']['balanceResidualM3']),1e-9)

    def test_unstable_shallow_impulse_fails_without_clipping(self):
        model=uniform(depth=.00002,step=1)
        model['wind']=numerical(model,speeds=(20.,),directions=(270.,))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FloodModelError,'TIMESTEP_UNSTABLE'):
                run(model,Path(tmp)/'unstable')

    def test_observed_wind_with_rainfall_preserves_rain_volume(self):
        from test_observed_surface_rainfall import specification
        from waterleague_sim.forcing.surface_run import run_observed_surface
        model=uniform(depth=.1,step=.5)
        model['boundaryConditions']={k:{'type':'REFLECTIVE'} for k in model['boundaryConditions']}
        model.update(schemaVersion=2,startUtc='2022-08-08T09:00:00Z',durationSeconds=120,wind=archived())
        with tempfile.TemporaryDirectory() as tmp:
            result=run_observed_surface(model,specification(model,end='2022-08-08T09:02:00Z'),Path(tmp)/'observed')
            self.assertEqual(result['numericalStatus'],'PASSED')
            self.assertTrue(result['wind']['complete'])
            self.assertGreater(abs(result['wind']['impulseXKgMps'])+abs(result['wind']['impulseYKgMps']),0)
            self.assertLess(abs(result['observedRainfall']['volumeResidualM3']),1e-8)
            self.assertLess(abs(result['final']['balanceResidualM3']),1e-6)
            self.assertTrue((Path(tmp)/'observed/surface/surface-wind-input/forcing-summary.json').is_file())


if __name__=='__main__':unittest.main()
