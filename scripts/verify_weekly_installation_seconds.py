"""공개 기상·옥상의 설치 초 경계와 주간 재현 입력 검증."""
import argparse
from datetime import datetime,timedelta
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'simulation'))
from waterleague_sim import shared_model
from waterleague_sim.engine.continuous import digest,engine_identity
from waterleague_sim.historical_antecedent import load as load_antecedent
from waterleague_sim.historical_evaporation import load as load_evaporation
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.weekly import aggregate,SECOND_RULE


def write(path,value):
    raw=(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n').encode()
    path.write_bytes(raw)
    return digest(raw)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    district='2419953';entry=shared_model.site_catalog(9)[district]
    cell='RW865253154'
    model,_,_=shared_model.resolve({'district_id':district,'cell_id':cell,'model_hash':entry['sha256']})
    observed_hash,raw=next((h,r) for h,r in read_catalog(ROOT/'data/models').items()
        if json.loads(r).get('mapId')=='seoul-osm-v1-'+district
        and json.loads(r).get('rainfall',{}).get('start','').startswith('2022-08-08'))
    observed=json.loads(raw);start=datetime.fromisoformat(observed['rainfall']['start'])
    installed=start+timedelta(seconds=17)
    write(out/'observed-model.json',observed)
    pet=load_evaporation(observed_hash,observed,out/'sources')
    antecedent=load_antecedent(observed_hash,out/'sources')
    results={};summaries=[]
    for name,minutes in [('prefix',2),('extended',5),('replay',5)]:
        directory=out/name;directory.mkdir()
        end=start+timedelta(minutes=minutes)
        weather=pet|{'ratesMmDay':pet['ratesMmDay'][:minutes]}
        source=shared_model.with_observed_forcing(model,weather)
        source['rainfall']=observed['rainfall']|{'end':end.isoformat(),'depthsMm':observed['rainfall']['depthsMm'][:minutes]}
        forcing=source['rainfall']|{'evaporation':weather,'evidence':'ARCHIVED_PUBLIC_WEATHER_REPLAY_NOT_CURRENT'}
        request={'schemaVersion':1,'installationId':'00000000-0000-4000-8000-000000000017',
            'modelSha256':write(directory/'model-source.json',source),
            'forcingSha256':write(directory/'forcing.json',forcing),
            'antecedentSha256':write(directory/'antecedent.json',antecedent),
            'siteModelHash':entry['sha256'],'engine':engine_identity(),
            'placement':{'cellId':cell,'facilityType':'GREEN_ROOF','areaM2':20.},
            'weeklyRuleVersion':SECOND_RULE,'installedAt':installed.isoformat(),
            'installationClock':'SERVER_SECOND_RESOLUTION_V1',
            'weeklyCodeSha256':digest((ROOT/'simulation/waterleague_sim/weekly.py').read_bytes())}
        write(directory/'request.json',request)
        for module in ['weekly.py','run_live_job.py']:
            shutil.copyfile(ROOT/'simulation/waterleague_sim'/module,directory/module)
        subprocess.run([sys.executable,'-m','waterleague_sim.run_live_job',str(directory)],
                       cwd=ROOT,check=True,timeout=90)
        result=json.loads((directory/'result.json').read_bytes());results[name]=result
        covered=start+timedelta(minutes=2) if name!='prefix' else installed
        weeks=aggregate(result['contribution'],installed,end,covered,rule=SECOND_RULE)
        summary={'name':name,'evaluationSeconds':sum(v['seconds'] for v in weeks.values()),
            'firstIntervalSeconds':result['strategy']['samples'][0]['elapsedSeconds'],
            'firstContributionM3':result['contribution'][0]['incrementM3'],
            'scoreM3':str(sum(v['score'] for v in weeks.values())),
            'maximumEvaluationBalanceResidualM3':max(abs(result[r]['final']['balanceResidualM3']) for r in ['baseline','strategy']),
            'nativeIntegratedSeconds':result['strategy']['runoffMetrics']['observedSeconds']}
        assert summary['evaluationSeconds']==minutes*60-17 and summary['firstIntervalSeconds']==43
        summaries.append(summary)
    assert results['extended']==results['replay']
    for case in ['baseline','strategy']:
        assert results['prefix'][case]['samples']==results['extended'][case]['samples'][:2]
        assert (out/'extended'/f'{case}.out').read_bytes()==(out/'replay'/f'{case}.out').read_bytes()
    for relative in ['backend/src/main/resources/shared-sites/catalog-v9.json',
        'backend/src/main/resources/shared-sites/'+entry['file'],'scripts/verify_weekly_installation_seconds.py',
        'simulation/waterleague_sim/shared_physics.py','simulation/uv.lock']:
        target=out/'source'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    report={'classification':'PUBLIC_SITE_WEEKLY_SECOND_BOUNDARY_REPLAY_NOT_LIVE_RANKING',
        'observedModelHash':observed_hash,'siteModelHash':entry['sha256'],'cellId':cell,
        'installedAt':installed.isoformat(),'firstIntervalSeconds':43,'cases':summaries,
        'prefixStatesIdentical':True,'replayIdentical':True,'nativeOutFilesIdentical':True,
        'limitations':['1분 강우의 분 내부 균일 강도와 서버 1초 시각 해상도',
            '7일 선행 기간에 시설이 존재한 초기 상태 가정; 시공 직후 현장 수분 아님',
            '현재 공개 옥상에 2022 기상을 적용한 독립 표면 시험; 당시 재현/연결 침수 아님',
            '시험용 설치 ID; 운영 회원/설치/점수 원장 변경 없음']}
    write(out/'report.json',report)
    files={str(p.relative_to(out)):digest(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'manifest.json',{'files':files})
    print(json.dumps(report|{'files':len(files),'manifestSha256':digest((out/'manifest.json').read_bytes())},ensure_ascii=False))


if __name__=='__main__':main()
