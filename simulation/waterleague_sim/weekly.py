"""분별 물리 산출물의 주간 합산·기존 적립 구간 보존."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from .evaluation.score_policy import quantize, verify

KST = timezone(timedelta(hours=9))
PRECISION = Decimal('0.000000001')
RULE = 'OBSERVED_ACCOUNTED_VOLUME_V1'
SECOND_RULE = 'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2'
SECOND_POLICY = 'INSTALLATION_SECOND_V2'


def aggregate(frames, start, end, covered, *, rule=RULE):
    if (rule not in (RULE, SECOND_RULE) or start.microsecond or end.second or end.microsecond
            or not start <= covered <= end or covered != start and (covered.second or covered.microsecond)):
        raise ValueError('LIVE_WEEKLY_INPUT_INVALID')
    weeks = {}
    last_time, last_score = start, Decimal(0)
    for frame in frames:
        at = datetime.fromisoformat(frame['at'])
        cumulative = Decimal(str(frame['cumulativeM3']))
        expected = last_time.replace(second=0, microsecond=0)+timedelta(minutes=1)
        if (rule == RULE and last_time.second) or at != expected or not cumulative.is_finite() or abs(cumulative) >= Decimal('1e15'):
            raise ValueError('LIVE_WEEKLY_INPUT_INVALID')
        cumulative = quantize(cumulative, 9)
        day = last_time.astimezone(KST).date()
        week = day-timedelta(days=day.weekday())
        value = weeks.setdefault(week, {'score': Decimal(0), 'minutes': 0, 'through': at,
                                       'prefixScore': Decimal(0), 'prefixMinutes': 0, 'prefixThrough': None,
                                       'seconds': 0, 'prefixSeconds': 0, 'rule': rule})
        value['score'] += cumulative-last_score
        value['minutes'] += 1
        value['seconds'] += int((at-last_time).total_seconds())
        value['through'] = at
        if at <= covered:
            value['prefixScore'] = value['score']
            value['prefixMinutes'] = value['minutes']
            value['prefixSeconds'] = value['seconds']
            value['prefixThrough'] = at
        last_time, last_score = at, cumulative
    if last_time != end or not weeks:
        raise ValueError('LIVE_WEEKLY_INPUT_INVALID')
    return weeks


def publish(conn, job, weeks):
    context = job.get('score_context')
    if not context or context.get('mode') != 'WEEKLY':
        raise ValueError('LIVE_SCORE_CONTEXT_INVALID')
    verify(context, 'WEEKLY', context['binding'])
    if any(value['rule'] != context['binding'] for value in weeks.values()):
        raise ValueError('LIVE_SCORE_CONTEXT_INVALID')
    previous = {r['week_start']: r for r in conn.execute(
        'SELECT * FROM shared_weekly_scores WHERE installation_id=%s FOR UPDATE', (job['installation']['id'],)).fetchall()}
    for week, old in previous.items():
        current = weeks.get(week)
        if (current is None or old['score_m3'] != current['prefixScore']
                or old.get('comparison_group_hash') != context['sha256']
                or old.get('score_policy_sha256') != context['policySha256']
                or old['evaluated_minutes'] != current['prefixMinutes']
                or old['evaluated_through'] != current['prefixThrough'] or old['rule_version'] != current['rule']
                or (old.get('evaluated_seconds') or old['evaluated_minutes']*60) != current['prefixSeconds']):
            raise ValueError('LIVE_WEEKLY_PREFIX_CHANGED')
    for week, value in weeks.items():
        conn.execute('''INSERT INTO shared_weekly_scores(installation_id,week_start,score_m3,
            evaluated_minutes,evaluated_through,source_job_id,rule_version,evaluated_seconds,
            score_policy_sha256,comparison_group_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(installation_id,week_start) DO UPDATE SET score_m3=EXCLUDED.score_m3,
            evaluated_minutes=EXCLUDED.evaluated_minutes,evaluated_seconds=EXCLUDED.evaluated_seconds,evaluated_through=EXCLUDED.evaluated_through,
            source_job_id=EXCLUDED.source_job_id WHERE shared_weekly_scores.evaluated_through<EXCLUDED.evaluated_through''',
            (job['installation']['id'], week, value['score'], value['minutes'], value['through'], job['id'], value['rule'],
             value['seconds'] if value['rule'] == SECOND_RULE else None, context['policySha256'], context['sha256']))
