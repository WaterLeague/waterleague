"""7일 선행 관측 강우·기상 입력. 최신 화면의 날씨 캐시로 사용하지 않음."""
from datetime import timedelta
from functools import partial
from . import evaporation, live, seoul_live
from .daily_evaporation import observed_daily
from ..engine.initialization import MINUTES

METHOD = 'OBSERVED_ANTECEDENT_WEATHER_V1'


def weather(start, end, key, daily_fetch=None, heartbeat=None):
    cursor, parts, sources = start, [], []
    while cursor < end:
        if heartbeat is not None: heartbeat()
        limit = min(end, cursor+timedelta(hours=23))
        if daily_fetch is None:
            value, raw = evaporation.observed_evaporation(cursor, limit, key, heartbeat=heartbeat)
        else:
            # 과거 초기화는 이전 완료 일의 관측만 사용하여 미래 정보 혼입 방지.
            day = cursor.astimezone(live.KST).replace(hour=0, minute=0)
            limit = min(end, day+timedelta(days=1))
            previous = day-timedelta(days=1)
            value, raw = observed_daily(previous, day, key, daily_fetch)
            value = value | {'method': 'FAO56_DAILY_LAGGED_ANTECEDENT_V1',
                'timePolicy': 'PREVIOUS_COMPLETED_DAY_HELD_OVER_NEXT_DAY',
                'ratesMmDay': [value['ratesMmDay'][0]]*int((limit-cursor).total_seconds()/60),
                'assumptions': [s for s in value['assumptions'] if s != '일 전체 확정 기상 사용; 실시간 계산에 사용 금지']
                    + ['이전 완료 일의 관측 기상으로 계산한 증발산을 다음 날에 유지; 일중 변화 미복원']}
        parts.append(value | {'start': cursor.isoformat(), 'end': limit.isoformat()})
        sources.extend(raw)
        cursor = limit
    return {'method': METHOD, 'ratesMmDay': [v for p in parts for v in p['ratesMmDay']],
        'sourceHashes': sorted({h for p in parts for h in p['sourceHashes']}),
        'sourceRequests': [s for p in parts for s in p['sourceRequests']], 'segments': parts,
        'assumptions': sorted({s for p in parts for s in p['assumptions']})}, sources


def fetch(station, evaluation_start, key, daily_fetch=None, heartbeat=None):
    start = evaluation_start-timedelta(minutes=MINUTES)
    rain, sources = live.observed_forcing(station, start, evaluation_start, key, chunk_hours=6,
        antecedent_quality=True, heartbeat=heartbeat, allow_gaps=True)
    rain, supplements = seoul_live.supplement(rain, start, evaluation_start, heartbeat=heartbeat)
    sources.extend(supplements)
    pet, raw = weather(start, evaluation_start, key,
                       daily_fetch or partial(evaporation.fetch, heartbeat=heartbeat), heartbeat)
    return {'rainfall': {k: rain[k] for k in ('start','end','stationId','intervalSeconds','sourceHashes','evidence','qualityWarnings','qualityPolicy','aggregatedRainIntervals')}
        | ({'supplement': rain['supplement']} if 'supplement' in rain else {})
        | {'depthsMm': [r['depthMm'] for r in rain['observations']], 'depthMethods': [r['method'] for r in rain['observations']],
           'reconstructedMinutes': sum(r['method'].startswith('OBSERVED_ZERO_') for r in rain['observations'])}, 'evaporation': pet}, sources+raw
