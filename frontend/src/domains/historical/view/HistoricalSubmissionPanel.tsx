import type { useHistoricalSubmission } from '../controller/useHistoricalSubmission';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
const time = (s: string) =>
  new Date(s).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
export function HistoricalSubmissionPanel({
  submission,
  draftCount,
  submit,
  authenticated,
  onLogin,
  designReady = true,
  designRevision,
  onReloadDesign,
  showAction = true,
}: {
  submission: ReturnType<typeof useHistoricalSubmission>;
  draftCount: number;
  submit: () => Promise<void>;
  authenticated: boolean;
  onLogin: () => void;
  designReady?: boolean;
  designRevision?: number;
  onReloadDesign?: () => void;
  showAction?: boolean;
}) {
  return (
    <section className="historical-submission" aria-label="재해 설계 제출">
      <h3>설계 확정·최종 점수</h3>
      {!authenticated && <p>시설 설치·진행 점수 체험 가능 · 제출과 최종 점수는 로그인 후 확인</p>}
      {authenticated && !!designRevision && <p>확정할 설계 저장본 {designRevision}</p>}
      <p>모든 구의 {draftCount}곳을 설치 시각과 무관하게 사건 시작부터 종료까지 다시 계산합니다.</p>
      <p>
        현재 형상·과거 강우의 독립 표면 평가체적 순위입니다. 실제 재난 복원과 침수 총점은 아직
        제공하지 않습니다.
      </p>
      {showAction && (
        <button
          className="solid-button"
          disabled={!designReady || submission.busy || !draftCount || draftCount > 50}
          onClick={() => (authenticated ? void submit() : onLogin())}
        >
          {submission.busy
            ? '설계 제출 중'
            : authenticated
              ? '설계 확정하고 제출'
              : '로그인 후 제출하기'}
        </button>
      )}
      {submission.error && <p role="alert">{submission.error}</p>}
      {submission.conflict && onReloadDesign && (
        <button disabled={submission.busy || !designReady} onClick={onReloadDesign}>
          저장된 설계 다시 불러오기
        </button>
      )}
      {submission.records.length > 0 && (
        <details open>
          <summary>내 제출 기록 · {submission.records.length}건</summary>
          {submission.records.map((record) => (
            <article key={record.id}>
              <strong>
                {time(record.createdAt)} · {record.placementCount}곳
                {record.designRevision != null && ` · 설계 저장본 ${record.designRevision} 확정`}
              </strong>
              <p>
                {record.state === 'SUCCEEDED' && record.result
                  ? `전체 기간 평가체적 감소 ${physicalAmount(record.result.differenceM3)} m³ · 기록 경쟁 게시`
                  : record.state === 'QUEUED'
                    ? '전체 기간 계산 대기'
                    : record.state === 'RUNNING'
                      ? '전체 기간 계산 중'
                      : '계산 실패 · 순위 미게시'}
              </p>
              {record.result && (
                <>
                  <p>
                    {time(record.result.start)} – {time(record.result.end)} KST
                  </p>
                  <a href={`/api/v1/historical/${record.id}/bundle`}>제출 재현 자료 다운로드</a>
                </>
              )}
            </article>
          ))}
        </details>
      )}
    </section>
  );
}
