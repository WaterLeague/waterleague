"""공개 식생수로 후보의 실제 관측 계산과 원문 재생 묶음 보관."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'simulation'), str(ROOT)]
from waterleague_sim import shared_model
from waterleague_sim.engine import continuous, initialization
from waterleague_sim.historical_antecedent import load as load_antecedent
from waterleague_sim.historical_evaporation import load as load_evaporation
from waterleague_sim.model_catalog import read_catalog


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    directory = parser.parse_args().output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    district = '2410520'
    entry = shared_model.site_catalog(8)[district]
    cell = next(c for c in shared_model.candidates(district, 8).values() if 'VEGETATIVE_SWALE' in c['allowedTypes'])
    model, _, _ = shared_model.resolve({'district_id':district,'cell_id':cell['id'],'model_hash':entry['sha256']})
    placement = {'cellId':cell['id'],'facilityType':'VEGETATIVE_SWALE','areaM2':cell['physicalInputs']['swaleDesign']['maxAreaM2']}
    records = read_catalog(ROOT/'data/models')
    model_hash, raw = next((key,raw) for key,raw in records.items()
        if json.loads(raw).get('mapId') == 'seoul-osm-v1-'+district
        and json.loads(raw).get('rainfall',{}).get('start','').startswith('2022-08-08'))
    observed = json.loads(raw)
    (directory/'observed-model.json').write_bytes(raw if isinstance(raw,bytes) else raw.encode())
    model['rainfall'] = observed['rainfall']
    pet = load_evaporation(model_hash, observed, directory/'sources')
    antecedent = load_antecedent(model_hash,directory/'sources')
    expanded, full_pet = initialization.prepend(model,pet,antecedent)
    result = continuous.experiment(expanded,placement,directory/'first',full_pet)
    replay = continuous.experiment(expanded,placement,directory/'replay',full_pet)
    if result != replay or any((directory/'first'/name).read_bytes() != (directory/'replay'/name).read_bytes()
                              for name in ('baseline.out','strategy.out')):
        raise ValueError('SWALE_REPLAY_MISMATCH')
    for relative in ('backend/src/main/resources/shared-sites/catalog-v8.json',
                     'backend/src/main/resources/shared-sites/'+entry['file'],
                     'data/costs/lid-reference-v4.json','scripts/swale_geometry.py',
                     'scripts/prepare_swale_sites.py','scripts/verify_map_swale.py','scripts/straight_footprint.py'):
        target=directory/'source'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/relative,target)
    final=result['strategy']['final']
    report={'schemaVersion':1,'classification':'PUBLIC_SITE_EXPLORATORY_DIRECT_RAIN_SWALE',
            'districtId':district,'cellId':cell['id'],'siteModelHash':entry['sha256'],
            'observedModelHash':model_hash,'rainStationId':model['rainfall']['stationId'],
            'evaluationRainMm':sum(model['rainfall']['depthsMm']),
            'placement':placement,'design':cell['physicalInputs']['swaleDesign'],
            'initialization':result['initialization'],'final':final,'runoffComparison':result['runoffComparison'],
            'referenceCostKrw':placement['areaM2']*45000,'exactReplay':True,
            'limitations':['공개 토성군의 문헌 투수계수·90m DEM 경사 대용값이며 현장 실측 아님',
                            '실제 시공·종단 경사·출구 미확인, 주변 배수/관망 연결 없음',
                            '2022 공개 계획 참고비이며 완전한 설치비·현재 견적 미확인']}
    write(directory/'report.json',report)
    files={str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'manifest.json',{'files':files})
    write(ROOT/'data/benchmarks/map-swale-v1.json',report | {'archive':str(directory.relative_to(ROOT)),
        'manifestSha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
        'files':len(files)})
    print(json.dumps({'exactReplay':True,'infiltrationM3':final['lidInfiltrationM3'],
        'surfaceRunoffM3':final['lidSurfaceRunoffM3'],'referenceCostKrw':report['referenceCostKrw'],
        'balanceResidualM3':final['balanceResidualM3'],'files':len(files)},ensure_ascii=False))

if __name__ == '__main__': main()
