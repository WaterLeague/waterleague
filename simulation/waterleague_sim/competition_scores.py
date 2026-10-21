"""참가 이후 설치의 원 계산 누적값을 고정 대회 종료 시각에서 절단."""
from datetime import datetime
from decimal import Decimal
from .evaluation.score_policy import quantize


def period_score(frames, installed_at, through):
    if through.second or through.microsecond:
        raise ValueError('LIVE_COMPETITION_BOUNDARY_INVALID')
    selected = None
    previous = installed_at
    for frame in frames:
        at = datetime.fromisoformat(frame['at'])
        if at <= previous:
            raise ValueError('LIVE_COMPETITION_FRAME_INVALID')
        previous = at
        if at <= through:
            amount = Decimal(str(frame['cumulativeM3']))
            if not amount.is_finite():
                raise ValueError('LIVE_COMPETITION_SCORE_INVALID')
            selected = (quantize(amount, 9), int((at-installed_at).total_seconds()), at)
    return selected


def publish(conn, job, frames):
    installation = job['installation']
    if installation['physics_policy'] != 'INSTALLATION_SECOND_V2':
        return
    context = job['score_context']
    competitions = conn.execute('''
        SELECT c.id,c.closes_at FROM game_competitions c
        JOIN game_competition_participants p ON p.competition_id=c.id
        JOIN accounts a ON a.id=p.owner_id JOIN organizations o ON o.id=c.organization_id
        WHERE c.mode='REALTIME' AND c.state='PUBLISHED' AND p.owner_id=%s
          AND c.opens_at<=%s AND c.closes_at>%s AND p.joined_at<=%s
          AND a.enabled=true AND a.approval_status='APPROVED' AND o.approved=true
          AND c.score_policy_sha256=%s
          AND jsonb_exists(c.rules::jsonb->'districtIds',%s)
          AND jsonb_exists(c.rules::jsonb->'allowedTypes',%s)
        ''', (installation['owner_id'], installation['installed_at'], installation['installed_at'],
              installation['installed_at'], context['policySha256'], installation['district_id'],
              installation['facility_type'])).fetchall()
    for competition in competitions:
        score = period_score(frames, installation['installed_at'], min(job['end'], competition['closes_at']))
        if score is None:
            continue
        amount, seconds, through = score
        conn.execute('''INSERT INTO game_competition_live_scores(
            competition_id,installation_id,owner_id,score_m3,evaluated_seconds,evaluated_through,
            comparison_group_hash,score_policy_sha256,source_job_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(competition_id,installation_id) DO UPDATE SET score_m3=EXCLUDED.score_m3,
            evaluated_seconds=EXCLUDED.evaluated_seconds,evaluated_through=EXCLUDED.evaluated_through,
            source_job_id=EXCLUDED.source_job_id
            WHERE game_competition_live_scores.evaluated_through<EXCLUDED.evaluated_through
              AND game_competition_live_scores.comparison_group_hash=EXCLUDED.comparison_group_hash
              AND game_competition_live_scores.score_policy_sha256=EXCLUDED.score_policy_sha256''',
            (competition['id'],installation['id'],installation['owner_id'],amount,seconds,through,
             context['sha256'],context['policySha256'],job['id']))
