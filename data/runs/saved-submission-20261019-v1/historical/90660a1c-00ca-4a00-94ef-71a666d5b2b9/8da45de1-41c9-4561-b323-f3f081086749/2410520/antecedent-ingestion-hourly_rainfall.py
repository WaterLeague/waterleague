"""동일 ASOS 지점의 공식 시간 강우를 선행 상태 계산에만 적용."""
from datetime import datetime, timedelta
from decimal import Decimal
from . import evaporation, live


def observed(station, start, end, key, fetch=None):
    if start.minute or start.second or end.minute or end.second:
        raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_ALIGNMENT_INVALID')
    if station != '108':
        raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_STATION_UNSUPPORTED')
    first = start.astimezone(live.KST).replace(minute=0)
    last = end.astimezone(live.KST).replace(minute=0)
    if end.minute:
        last += timedelta(hours=1)
    if last > end:
        raise live.LiveSourceError('KMA_ANTECEDENT_FUTURE_HOUR_REJECTED')
    raw, source = (fetch or evaporation.fetch)(evaporation.HOURLY_URL,
        {'tm1':first.strftime('%Y%m%d%H%M'),'tm2':last.strftime('%Y%m%d%H%M'),'stn':station,'help':'1'},key)
    rows = {}
    for fields in evaporation.lines(raw):
        if len(fields)!=46 or fields[1]!=station:
            raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_FORMAT_INVALID')
        at = datetime.strptime(fields[0],'%Y%m%d%H%M').replace(tzinfo=live.KST)
        if at in rows or at.minute or not first<=at<=last:
            raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_FORMAT_INVALID')
        values = [Decimal(fields[i]) for i in (15,16)]
        if any(not v.is_finite() or v>5000 for v in values):
            raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_FORMAT_INVALID')
        rows[at] = values
    sources = [(raw,source)]
    minute_rows, cursor = {}, start-timedelta(minutes=61)
    while cursor < end:
        limit = min(end,cursor+timedelta(hours=6))
        raw, meta = live.fetch_range(station,cursor,limit,key)
        minute_rows.update(live.parse(raw,station,cursor,limit));sources.append((raw,meta));cursor=limit
    warnings = []
    minute_values = {datetime.fromisoformat(v['end']):v for v in live.normalized(minute_rows,start,end,
        allow_gaps=True,rolling_warnings=warnings)}
    depths, methods, intervals = [], [], []
    cursor = start
    while cursor < end:
        limit = cursor+timedelta(hours=1)
        minutes = [minute_values.get(cursor+timedelta(minutes=i)) for i in range(1,61)]
        if all(v is not None for v in minutes):
            depths += [v['depthMm'] for v in minutes]; methods += [v['method'] for v in minutes]
            cursor = limit
            continue
        current, previous = rows.get(limit), rows.get(cursor)
        if current is None or previous is None:
            raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_MISSING')
        rain, day = current
        if rain < 0:
            if day == previous[1] and day >= 0 and limit.hour != 1:
                rain = Decimal(0)
            elif day == 0 and limit.hour == 1:
                rain = Decimal(0)
            else:
                raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_MISSING')
        if not 0 <= rain <= 500:
            raise live.LiveSourceError('KMA_ANTECEDENT_HOURLY_INVALID')
        depths += [float(rain/60)]*60
        methods += ['OBSERVED_HOURLY_MEAN_ASSUMPTION']*60
        intervals.append({'start':cursor.isoformat(),'end':limit.isoformat(),'minutes':60,
            'totalMm':float(rain),'timeDistribution':'OBSERVED_HOURLY_MEAN_NOT_MINUTE_OBSERVATIONS'})
        cursor = limit
    return {'stationId':station,'start':start.isoformat(),'end':end.isoformat(),'intervalSeconds':60,
        'depthsMm':depths,'depthMethods':methods,'sourceHashes':[m['sha256'] for _,m in sources],
        'sourceRequests':[m for _,m in sources], 'evidence':'OBSERVED_AWS_MINUTE_AND_ASOS_HOURLY_INTERVAL_MEAN',
        'qualityWarnings':warnings, 'qualityPolicy':'SAME_STATION_ASOS_HOURLY_FALLBACK_FOR_INITIALIZATION_ONLY',
        'aggregatedRainIntervals':intervals,'reconstructedMinutes':sum(m.startswith('OBSERVED_ZERO_') for m in methods)}, sources
