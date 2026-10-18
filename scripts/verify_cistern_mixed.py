"""혼합 집수 이용조의 면적·원 유출 보존과 회원 계산 재생 묶음."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.run_watershed_job import calculate, inputs, write
from waterleague_sim.watershed_replay import replay
from waterleague_sim.engine.cistern_network import compile_cistern
from waterleague_sim.ingestion.published_network import digest, records
from waterleague_sim.reference.cistern_network import source, design, hydrology_series


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    directory=args.output.resolve();directory.mkdir(parents=True, exist_ok=False)
    request=json.loads(args.request.read_text())
    catalog,_,base,_,_,transformed,_=inputs(request)
    if transformed['networkCistern']['schemaVersion'] != 2:
        raise ValueError('MIXED_CISTERN_REQUIRED')
    write(directory/'request.json',request)
    member=directory/'member'
    result=calculate(request,member)
    result['artifactFiles']={str(p.relative_to(member)):digest(p.read_bytes()) for p in sorted(member.rglob('*')) if p.is_file()}
    write(member/'result.json',result)
    write(member/'manifest.json',{str(p.relative_to(member)):digest(p.read_bytes()) for p in sorted(member.rglob('*')) if p.is_file()})
    replayed=replay(member,directory/'replay')
    comparisons=[]
    for percent in (25,80):
        raw=source(backwater=True).replace(b'0.01 100 10',f'0.01 {percent} 10'.encode())
        raw=raw.replace(b'.013 .15 0 0 100 OUTLET',b'.013 .15 2 5 35 OUTLET')
        raw=raw.replace(b'[REPORT]',b'[EVAPORATION]\nCONSTANT 2\n[REPORT]\nSUBCATCHMENTS ALL')
        spec=design(raw)|{'schemaVersion':2,'captureAreaM2':10}
        derived,meta=compile_cistern(raw,spec)
        before=hydrology_series(raw,directory/f'diagnostic-{percent}-base')
        after=hydrology_series(derived,directory/f'diagnostic-{percent}-strategy')
        differences={key:max(abs(a-b) for a,b in zip(before[key],after[key])) for key in before}
        if not all(len(before[key])==len(after[key]) and all(abs(a-b)<=max(1e-9,abs(a)*2e-7)
            for a,b in zip(before[key],after[key])) for key in before):
            raise ValueError('MIXED_SURFACE_HYDROLOGY_CHANGED')
        values={'classification':'NUMERICAL_DIAGNOSTIC_NOT_SEOUL','imperviousPercent':percent,
            'design':spec,'partition':meta['catchmentPartition'],'before':before,'after':after,'maxAbsoluteDifferences':differences}
        write(directory/f'diagnostic-{percent}.json',values)
        comparisons.append({k:values[k] for k in ('imperviousPercent','maxAbsoluteDifferences')})
    # 공개 원본 모든 구역의 연결·높이 범위를 사용하되 실제 설치 위치를 만들지 않는다.
    sections=records(base)[1]
    nodes={r['tokens'][0]:r['tokens'] for r in sections['JUNCTIONS']}
    eligible=[]
    for row in catalog['catchments']:
        p={k:v for k,v in json.loads(request['placements'])['cistern'].items() if k!='catalogHash'}
        floor=float(nodes[row['outletNodeId']][1])
        p.update(schemaVersion=1 if row['imperviousM2']==row['areaM2'] else 2,
            sourceNetworkSha256=digest(base),subcatchmentId=row['id'],invertM=floor)
        p['drain']=p['drain']|{'crestM':floor+.05}
        p['overflow']=p['overflow']|{'crestM':floor+1.55}
        _,meta=compile_cistern(base,p)
        eligible.append({'id':row['id'],'schemaVersion':p['schemaVersion'],'partition':meta['catchmentPartition']})
    shutil.copyfile(Path(__file__),directory/'verify_cistern_mixed.py')
    report={'schemaVersion':1,'classification':'PUBLIC_NETWORK_MIXED_SURFACE_CISTERN_DESIGN',
        'sourceUrl':catalog['sourceUrl'],'sourceOriginalSha256':catalog['sourceOriginalSha256'],
        'numericalStatus':result['numericalStatus'],'partition':transformed['networkCistern']['catchmentPartition'],
        'signedReductionM3':result['signedReductionM3'],'signedPeakReductionM3s':result['signedPeakReductionM3s'],
        'storageLedger':result['cases'][1]['networkCistern']['wholeRunLedger'],
        'runoffInflowDifferenceM3':result['cases'][1]['totals']['runoffInflowM3']-result['cases'][0]['totals']['runoffInflowM3'],
        'diagnostics':comparisons,'eligibleCatchments':eligible,'replay':replayed,
        'rankingEligible':False,'mapInstallationEnabled':False,
        'limitations':['공개 연구 관망의 명시적 설계 비교이며 실제 지붕·홈통 위치 미확인',
            '분할의 수문 보존과 관망 수치 통과는 현장 침수 검증이 아님',
            '작은 효과 차이의 수치 오차 대비 견고성·관측 유의성 미확정; 경쟁 점수 미적용']}
    write(directory/'report.json',report)
    files={str(p.relative_to(directory)):digest(p.read_bytes()) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'manifest.json',{'files':files})
    write(ROOT/'data/benchmarks/cistern-mixed-v1.json',report|{'archive':str(directory.relative_to(ROOT)),
        'files':len(files),'manifestSha256':digest((directory/'manifest.json').read_bytes())})
    print(json.dumps({'status':result['numericalStatus'],'eligibleCatchments':len(eligible),'exactReplay':True,
        'runoffInflowDifferenceM3':report['runoffInflowDifferenceM3'],'files':len(files)},ensure_ascii=False))


if __name__=='__main__': main()
