"""분별 물리 산출물의 주간 합산·기존 적립 구간 보존."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN

KST = timezone(timedelta(hours=9))
PRECISION = Decimal('0.000000001')
RULE = 'OBSERVED_ACCOUNTED_VOLUME_V1'


def aggregate(frames, start, end, covered):
    weeks = {}
    last_time, last_score = start, Decimal(0)
    for frame in frames:
        at = datetime.fromisoformat(frame['at'])
        cumulative = Decimal(str(frame['cumulativeM3']))
        if at != last_time+timedelta(minutes=1) or not cumulative.is_finite() or abs(cumulative) >= Decimal('1e15'):
            raise ValueError('LIVE_WEEKLY_INPUT_INVALID')
        cumulative = cumulative.quantize(PRECISION, rounding=ROUND_HALF_EVEN)
        day = (at-timedelta(minutes=1)).astimezone(KST).date()
        week = day-timedelta(days=day.weekday())
        value = weeks.setdefault(week, {'score': Decimal(0), 'minutes': 0, 'through': at,
                                       'prefixScore': Decimal(0), 'prefixMinutes': 0, 'prefixThrough': None})
        value['score'] += cumulative-last_score
        value['minutes'] += 1
        value['through'] = at
        if at <= covered:
            value['prefixScore'] = value['score']
            value['prefixMinutes'] = value['minutes']
            value['prefixThrough'] = at
        last_time, last_score = at, cumulative
    if last_time != end or not weeks:
        raise ValueError('LIVE_WEEKLY_INPUT_INVALID')
    return weeks


def publish(conn, job, weeks):
    previous = {r['week_start']: r for r in conn.execute(
        'SELECT * FROM shared_weekly_scores WHERE installation_id=%s FOR UPDATE', (job['installation']['id'],)).fetchall()}
    for week, old in previous.items():
        current = weeks.get(week)
        if (current is None or old['score_m3'] != current['prefixScore']
                or old['evaluated_minutes'] != current['prefixMinutes']
                or old['evaluated_through'] != current['prefixThrough'] or old['rule_version'] != RULE):
            raise ValueError('LIVE_WEEKLY_PREFIX_CHANGED')
    for week, value in weeks.items():
        conn.execute('''INSERT INTO shared_weekly_scores(installation_id,week_start,score_m3,
            evaluated_minutes,evaluated_through,source_job_id,rule_version) VALUES(%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(installation_id,week_start) DO UPDATE SET score_m3=EXCLUDED.score_m3,
            evaluated_minutes=EXCLUDED.evaluated_minutes,evaluated_through=EXCLUDED.evaluated_through,
            source_job_id=EXCLUDED.source_job_id WHERE shared_weekly_scores.evaluated_through<EXCLUDED.evaluated_through''',
            (job['installation']['id'], week, value['score'], value['minutes'], value['through'], job['id'], RULE))
