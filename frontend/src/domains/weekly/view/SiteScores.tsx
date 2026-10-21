import { scoreDuration } from '../service/scoreDuration';
import { useSiteScores } from '../controller/useSiteScores';
import { facilities } from '../../game/service/gameService';
import type { SiteScoresPage } from '../dto/siteScoresDto';
import { scoreFormat } from '../service/scoreFormat';
export function SiteScoreRows({
  value,
  viewerId,
}: {
  value: SiteScoresPage;
  viewerId: string | null;
}) {
  return (
    <>
      {value.installations.map((i) => (
        <article key={i.id}>
          <b>
            {i.ownerId === viewerId ? '내 시설' : i.ownerName} · {facilities[i.facilityType].name}
          </b>
          <p>
            {i.areaM2.toLocaleString('ko-KR')} m² · 누적 기여{' '}
            <strong>
              {i.scoreM3 === null ? '점수 없음' : `${scoreFormat.format(i.scoreM3)} m³`}
            </strong>
          </p>
          <small>
            설치 {new Date(i.installedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST
          </small>
          {i.evaluatedThrough && (
            <small>
              계산 반영{' '}
              {new Date(i.evaluatedThrough).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST
              · {scoreDuration(i)}
            </small>
          )}
        </article>
      ))}
    </>
  );
}
export function SiteScores({
  districtId,
  cellId,
  viewerId,
}: {
  districtId: string;
  cellId: string;
  viewerId: string | null;
}) {
  const state = useSiteScores(districtId, cellId);
  return (
    <section className="weekly-site-scores" aria-label="이 위치의 회원별 시설 점수">
      <h3>이 위치의 시설별 누적 점수</h3>
      <p className="micro-note">
        회원별 설계는 독립 비교합니다. 이 위치에 다른 회원이 설치해도 내 시설을 설치할 수 있습니다.
      </p>
      {state.error && <p role="status">{state.error}</p>}
      {!state.value ? (
        !state.error && <p>시설 기록 조회 중</p>
      ) : (
        <>
          <SiteScoreRows value={state.value} viewerId={viewerId} />
          {!state.value.installations.length && <p>이번 시즌에 설치된 시설이 없습니다.</p>}
          {(state.hasPrevious || state.value.nextAfterId) && (
            <div className="shared-list-pages">
              <button onClick={state.previous} disabled={!state.hasPrevious}>
                이전
              </button>
              <button onClick={state.next} disabled={!state.value.nextAfterId}>
                다음
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
