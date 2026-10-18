"""실제 보관 풍속·강우의 수면 운동량/체적·시간/격자 비교와 재현 원본 보존."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'simulation'))
from verify_observed_surface_rainfall import specification
from waterleague_sim.forcing.surface_wind import POLICY
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n')


def wind_spec():
    name='seoul-20220808-fao56-v1.json'
    return {'schemaVersion':1,'policyVersion':POLICY,'type':'ARCHIVED_KMA_AWS',
        'reference':{'file':name,'sha256':sha(ROOT/'data/derived/evaporation'/name)},
        'integrationPolicy':'FROZEN_DRAG_EXACT_RELATIVE_V1',
        'heightCorrection':'POWER_LAW_ONE_SEVENTH_UNCALIBRATED',
        'airDensityKgM3':1.29,'waterDensityKgM3':1000.,'dragLaw':'GARRATT_HEC_6_6',
        'vectorBasis':'LOCAL_TRUE_EAST_NORTH_DIAGNOSTIC',
        'evidence':'서울 108 바람을 합성 수면에 균일 적용; 지형/차폐/현장 바람 미보정',
        'densityEvidence':'HEC-RAS 공기밀도 근사와 담수 1000kg/m³ 고정 가정'}


def domain(nx,step):
    model=mesh(nx,nx,100,100,water=lambda x,z:x*0+.02)
    model.update(schemaVersion=2,startUtc='2022-08-08T09:00:00Z',durationSeconds=3600,
        evidence='OBSERVED_WEATHER_ON_SYNTHETIC_WATER_SURFACE_NOT_SEOUL',maxStepSeconds=step,
        wind=wind_spec(),frameOutput={'schemaVersion':1,'type':'NATIVE_CENTROID_FLOAT64',
                                     'maxFrames':120,'maxBytes':16*1024**2})
    return model


def restricted_depths(coarse, fine, values):
    from shapely.geometry import Polygon, Point
    shapes=[Polygon([coarse['verticesM'][v] for v in t]) for t in coarse['triangles']]
    totals,areas=[0.]*len(shapes),[0.]*len(shapes)
    for triangle,value in zip(fine['triangles'],values):
        shape=Polygon([fine['verticesM'][v] for v in triangle]);center=shape.centroid
        cells=[i for i,p in enumerate(shapes) if p.contains(center)]
        require(len(cells)==1,'WIND_GRID_RESTRICTION_AMBIGUOUS')
        i=cells[0];totals[i]+=value*shape.area;areas[i]+=shape.area
    require(all(a>0 for a in areas),'WIND_GRID_RESTRICTION_INCOMPLETE')
    return [v/a for v,a in zip(totals,areas)]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    out=args.output.resolve();require(not out.exists(),'WIND_VERIFICATION_OUTPUT_EXISTS');out.mkdir(parents=True)
    sources=[Path(__file__),ROOT/'scripts/verify_observed_surface_rainfall.py',ROOT/'simulation/uv.lock',
             ROOT/'simulation/pyproject.toml',ROOT/'data/manifests/anuga-4.0.1.json',
             ROOT/'data/manifests/wind-stress-references-v1.json']
    for folder in ['engine','forcing','reference','ingestion']:
        sources+=sorted((ROOT/'simulation/waterleague_sim'/folder).glob('*.py'))
    for path in sources:
        target=out/'source'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    references=json.loads((ROOT/'data/manifests/wind-stress-references-v1.json').read_bytes())
    for row in references['sources']:
        path=ROOT/row['path'];require(sha(path)==row['sha256'],'WIND_REFERENCE_HASH_MISMATCH')
        target=out/row['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    results,models,cases={},{},[]
    for name,nx,step,wind in [('step-1s',4,1.,True),('step-05s',4,.5,True),('step-025s',4,.25,True),
                            ('grid-8',8,.25,True),('grid-16',16,.25,True),('replay-05s',4,.5,True),
                            ('without-wind',4,.5,False)]:
        model=domain(nx,step)
        if not wind:model.pop('wind')
        result=run_observed_surface(model,specification(model,minutes=60,two_stations=False),out/name)
        results[name],models[name]=result,model
        native=json.loads((out/name/'surface/surface-result.json').read_bytes())
        cases.append({'name':name,'triangles':len(model['triangles']),'maximumStepSeconds':step,
            'status':result['numericalStatus'],'final':result['final'],'wind':result.get('wind'),
            'rainfallVolumeResidualM3':result['observedRainfall']['volumeResidualM3'],
            'maximumInternalBalanceResidualM3':result['numericalQuality']['maximumAbsoluteResidualM3'],
            'surfaceResultSha256':sha(out/name/'surface/surface-result.json'),
            'frameCount':len(json.loads((out/name/'surface/native-frames/catalog.json').read_bytes())['frames'])})
        require(result['numericalStatus']=='PASSED','WIND_DIAGNOSTIC_NUMERICS_FAILED')
        print(name,{'balanceM3':result['final']['balanceResidualM3'],
                    'depthRangeM':[min(result['final']['depthM']),max(result['final']['depthM'])]},flush=True)
    depths=lambda name:results[name]['final']['depthM']
    delta=lambda a,b:max(abs(x-y) for x,y in zip(a,b))
    grid4=depths('step-025s')
    grid8=restricted_depths(models['step-025s'],models['grid-8'],depths('grid-8'))
    grid16=restricted_depths(models['step-025s'],models['grid-16'],depths('grid-16'))
    comparison={'exactReplay':results['step-05s']['final']==results['replay-05s']['final']
            and results['step-05s']['wind']==results['replay-05s']['wind'],
        'time1To05MaxDepthDifferenceM':delta(depths('step-1s'),depths('step-05s')),
        'time05To025MaxDepthDifferenceM':delta(depths('step-05s'),grid4),
        'grid4To8MaxAreaMeanDepthDifferenceM':delta(grid4,grid8),
        'grid8To16MaxAreaMeanDepthDifferenceM':delta(grid8,grid16),
        'windToNoWindMaxDepthDifferenceM':delta(depths('step-05s'),depths('without-wind'))}
    comparison['timeDifferenceDecreased']=comparison['time05To025MaxDepthDifferenceM']<comparison['time1To05MaxDepthDifferenceM']
    comparison['gridDifferenceDecreased']=comparison['grid8To16MaxAreaMeanDepthDifferenceM']<comparison['grid4To8MaxAreaMeanDepthDifferenceM']
    require(comparison['exactReplay'],'WIND_REPLAY_FAILED')
    # 불안정한 명시 적분 실패도 보존하여 성공 사례만으로 수치 범위를 숨기지 않는다.
    model=domain(2,1.);model['initialDepthM']=[.00002]*len(model['triangles'])
    model.update(evidence='NUMERICAL_TEST_ONLY_NOT_SEOUL',durationSeconds=60)
    model['wind']=wind_spec()|{'type':'NUMERICAL_TEST_SERIES','measurementHeightM':10.,
        'dragLaw':'CONSTANT_NUMERICAL_ONLY','constantDragCoefficient':.001,
        'integrationPolicy':'ANUGA_EXPLICIT_DIAGNOSTIC_V1',
        'intervals':[{'startUtc':model['startUtc'],'endUtc':'2022-08-08T09:01:00Z','speedMs':20.,'fromDegrees':270.}]}
    failure=None
    try:
        with EngineProcess('surface',model,out/'explicit-unstable') as session:session.call('advance',60)
    except FloodModelError as error:failure=str(error)
    require(failure=='WIND_TIMESTEP_UNSTABLE','WIND_EXPECTED_FAILURE_MISSING')
    summary={'schemaVersion':1,'classification':'OBSERVED_WIND_ENGINE_DIAGNOSTIC_NOT_SEOUL_FLOOD',
        'rankingEligible':False,'cases':cases,'comparison':comparison,'preservedFailure':failure,
        'limitations':['합성 100×100m 수면·2cm 초기수심·반사 경계; 실제 서울 지형/배수/침수 아님',
            '서울 108 바람과 성동 421 강우의 합성 공간 결합; 바람 공간 대표성 미검증',
            '풍속계 7m 지상 높이를 수면 높이로 대응하는 해상 1/7 환산 미보정',
            '시간·격자 차이 감소는 현장 정확성 검증이 아님']}
    write(out/'summary.json',summary)
    files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'artifact-manifest.json',{'schemaVersion':1,'files':files})
    print(json.dumps({'comparison':comparison,'files':len(files),'manifestSha256':sha(out/'artifact-manifest.json')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
