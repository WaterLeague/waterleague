"""보관 풍응력 진단의 입력을 유지한 추가 격자 세분 검사."""
import argparse
import json
from pathlib import Path
import shutil
from verify_surface_wind import ROOT, sha, write, restricted_depths, domain, specification, run_observed_surface, require


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    source=args.source.resolve();out=args.output.resolve()
    manifest=json.loads((source/'artifact-manifest.json').read_bytes())
    for path,digest in manifest['files'].items():
        require(sha(source/path)==digest,'WIND_BASE_ARCHIVE_MODIFIED')
    # 다른 코드로 계산한 결과에 원 실행의 소스 출처를 붙이지 않는다.
    for path in sorted((source/'source').rglob('*')):
        if path.is_file():
            current=ROOT/path.relative_to(source/'source')
            require(current.is_file() and sha(current)==sha(path),'WIND_REFINEMENT_SOURCE_CHANGED')
    require(not out.exists(),'WIND_REFINEMENT_OUTPUT_EXISTS');out.mkdir(parents=True)
    shutil.copytree(source/'source',out/'source')
    target=out/'source/scripts/verify_surface_wind_refinement.py';shutil.copyfile(Path(__file__),target)
    coarse=json.loads((source/'step-025s/observed-surface-input.json').read_bytes())['surface']
    prior=json.loads((source/'grid-16/observed-surface-result.json').read_bytes())['final']['depthM']
    prior_model=json.loads((source/'grid-16/observed-surface-input.json').read_bytes())['surface']
    restricted=restricted_depths(coarse,prior_model,prior)
    cases=[]
    for size in (32,64):
        model=domain(size,.25)
        result=run_observed_surface(model,specification(model,minutes=60,two_stations=False),out/f'grid-{size}')
        require(result['numericalStatus']=='PASSED','WIND_REFINEMENT_NUMERICS_FAILED')
        current=restricted_depths(coarse,model,result['final']['depthM'])
        difference=max(abs(a-b) for a,b in zip(restricted,current))
        row={'name':f'grid-{size}','triangles':len(model['triangles']),'status':result['numericalStatus'],
            'maximumAreaMeanDepthDifferenceFromPreviousGridM':difference,
            'relativeToMeanDepthPercent':100*difference/(result['final']['storageM3']/10000),
            'maximumBalanceResidualM3':result['numericalQuality']['maximumAbsoluteResidualM3'],
            'finalStorageM3':result['final']['storageM3'],'depthRangeM':[min(result['final']['depthM']),max(result['final']['depthM'])],
            'surfaceResultSha256':sha(out/f'grid-{size}/surface/surface-result.json')}
        cases.append(row);restricted=current
        print(json.dumps(row),flush=True)
    write(out/'summary.json',{'schemaVersion':1,'classification':'OBSERVED_WIND_NUMERICAL_GRID_REFINEMENT_NOT_SEOUL',
        'rankingEligible':False,'baseManifestSha256':sha(source/'artifact-manifest.json'),'cases':cases,
        'restriction':'AREA_WEIGHTED_RESTRICTION_TO_FIXED_4_BY_4_GRID','fixedPhysicalInputs':True})
    files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'artifact-manifest.json',{'schemaVersion':1,'files':files})
    print(json.dumps({'files':len(files),'manifestSha256':sha(out/'artifact-manifest.json')}),flush=True)


if __name__=='__main__':main()
