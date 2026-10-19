"""공개 기준안 격리 계산. 비밀값은 계산 입력·산출물에 저장하지 않는다."""
import os
from pathlib import Path
import sys

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.live_rainfall import capture, extend
from waterleague_sim.forcing.observed_rainfall import utc
from waterleague_sim.ingestion.live import LiveSourceError
from waterleague_sim.ingestion.rainfall import RainfallQualityError
from .repository import read, decode, atomic_json


def execute(directory, key):
    request=decode(read(directory/'request.json'))
    rainfall=request['rainfall']; model=request['model']
    start,end=utc(rainfall['startUtc']),utc(rainfall['endUtc'])
    from waterleague_sim.engine.coupled_flood import _validate
    _validate(model)
    if (directory/'previous-input.json').exists():
        old=decode(read(directory/'previous-input.json'))
        previous=old['observedRainfall']
        require(utc(previous['startUtc'])==start and all(previous.get(k)==rainfall.get(k) for k in
            ('stationByTriangle','stationByCatchment','assignmentEvidence')),'PUBLIC_SURFACE_FORCING_LINEAGE_MISMATCH')
        specification=extend(previous,end,key)
    else:
        binding={'network':model['network'],'station_by_catchment':rainfall['stationByCatchment']} if 'stationByCatchment' in rainfall else {}
        specification=capture(model['surface'],rainfall['stationByTriangle'],start,end,key,
                              rainfall['assignmentEvidence'],**binding)
    result=run_coupled(model | {'observedRainfall':specification},directory/'calculation')
    require(result['numericalStatus']=='PASSED','PUBLIC_SURFACE_NUMERICAL_FAILURE')
    return result


def main():
    os.umask(0o077)
    directory=Path(sys.argv[1]).resolve()
    try:
        execute(directory,os.environ.get('KMA_API_KEY',''))
        atomic_json(directory/'completion.json',{'status':'SUCCEEDED'})
    except (FloodModelError,LiveSourceError,RainfallQualityError) as error:
        code=str(error)
        # 원 예외 본문·서버 응답은 외부 상태 파일에 복사하지 않는다.
        if not code or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in code):
            code='PUBLIC_SURFACE_CALCULATION_FAILED'
        atomic_json(directory/'completion.json',{'status':'FAILED','errorCode':code})
        raise SystemExit(1) from None
    except (ValueError,TypeError,KeyError,OSError):
        atomic_json(directory/'completion.json',{'status':'FAILED','errorCode':'PUBLIC_SURFACE_CALCULATION_FAILED'})
        raise SystemExit(1) from None


if __name__=='__main__':main()
