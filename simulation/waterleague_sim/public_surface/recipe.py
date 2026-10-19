"""고정 시작 상태의 연속 재생 기간과 평가 창 구성. 물성·경계 변경 없음."""
from copy import deepcopy
from datetime import timedelta

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.forcing.observed_rainfall import utc
from waterleague_sim.forcing.network_initialization import _date
from waterleague_sim.ingestion.published_network import records
from .repository import CLASSIFICATION

POLICY='CONTINUOUS_REPLAY_FROM_FROZEN_ORIGIN_V1'


def request(recipe, cutoff):
    require(isinstance(recipe,dict) and set(recipe)=={'schemaVersion','statePolicy','startUtc',
        'evaluationStartUtc','endBeforeUtc','model','rainfall'} and recipe['schemaVersion']==1
        and recipe['statePolicy']==POLICY,'PUBLIC_SURFACE_RECIPE_INVALID')
    start,evaluation,stop=[utc(recipe[k]) for k in ('startUtc','evaluationStartUtc','endBeforeUtc')]
    require(all(v.second==v.microsecond==0 for v in (start,evaluation,stop,cutoff))
            and 7*86400<=(evaluation-start).total_seconds()<=28*86400
            and evaluation<cutoff<=stop and 0<(cutoff-start).total_seconds()<=29*86400,
            'PUBLIC_SURFACE_WINDOW_INVALID')
    model=deepcopy(recipe['model']); duration=int((cutoff-start).total_seconds())
    surface=model['surface']; network=model['network']; metrics=model.get('evaluationMetrics')
    require(model.get('evidence')==surface.get('evidence')==CLASSIFICATION
            and isinstance(metrics,dict) and isinstance(surface.get('terrainProvenance'),dict)
            and surface['terrainProvenance'].get('absoluteVerticalReferenceVerified') is True
            and surface.get('frameOutput',{}).get('type')=='NATIVE_CENTROID_FLOAT64',
            'PUBLIC_SURFACE_INPUT_EVIDENCE_REQUIRED')
    require(not any(k in model for k in ('observedRainfall','initialization','surfaceRainfall',
        'connectedFacilityDesign','connectedStorageDesign','connectedPumpDesign')),
        'PUBLIC_SURFACE_FORCING_COMPOSITION_UNSUPPORTED')
    _,sections=records(network['inputText'].encode())
    options={r['tokens'][0].upper():r['tokens'][1] for r in sections['OPTIONS'] if len(r['tokens'])==2}
    require({'START_DATE','START_TIME','REPORT_START_DATE','REPORT_START_TIME'}<=options.keys()
            and network.get('timeZone')=='UTC' and _date(options['START_DATE'],options['START_TIME'])==start
            and _date(options['REPORT_START_DATE'],options['REPORT_START_TIME'])==start,
            'PUBLIC_SURFACE_ORIGIN_MISMATCH')
    replacements={'END_DATE':f'{cutoff+timedelta(seconds=1):%m/%d/%Y}',
                  'END_TIME':f'{cutoff+timedelta(seconds=1):%H:%M:%S}'}
    lines=network['inputText'].splitlines(); touched=set()
    for row in sections['OPTIONS']:
        key=row['tokens'][0].upper()
        if key in replacements:
            require(key not in touched,'PUBLIC_SURFACE_CLOCK_DUPLICATE')
            touched.add(key);lines[row['line']-1]=key+' '+replacements[key]
    require(touched==set(replacements),'PUBLIC_SURFACE_CLOCK_INVALID')
    network['inputText']='\n'.join(lines)+'\n'
    if 'startUtc' in network or 'durationSeconds' in network:
        network.update(startUtc=start.isoformat(),durationSeconds=duration)
    surface.update(startUtc=start.isoformat(),durationSeconds=duration)
    model['durationSeconds']=duration
    metrics.update(startMilliseconds=int((evaluation-start).total_seconds())*1000,endMilliseconds=duration*1000)
    require(isinstance(recipe['rainfall'],dict) and set(recipe['rainfall']) in (
        {'stationByTriangle','assignmentEvidence'}, {'stationByTriangle','assignmentEvidence','stationByCatchment'}),
        'PUBLIC_SURFACE_RAINFALL_INVALID')
    return {'mode':'coupled','model':model,'rainfall':deepcopy(recipe['rainfall']) | {
        'startUtc':start.isoformat(),'endUtc':cutoff.isoformat()}}
