import { useReviewWorkspace } from '../controller/useReviewWorkspace';
import type { ReviewState } from '../entity/utilization';
import { ReviewRecords } from './ReviewRecords';
export function ReviewWorkspace({
  jobId,
  onRequested,
}: {
  jobId: string;
  onRequested: () => void;
}) {
  const u = useReviewWorkspace(jobId, onRequested);
  return (
    <section className="review-workspace">
      <h3>이 계산에 대한 기관 검토</h3>
      <p>
        소속 기관의 의견을 기록하고, 설계 소유자와 확인할 조건을 공유합니다. 현장 적용 승인은
        아닙니다.
      </p>
      {u.error && (
        <p className="form-error" role="alert">
          {u.error}
        </p>
      )}
      {u.notice && (
        <p className="utilization-notice" role="status">
          {u.notice}
        </p>
      )}
      <details>
        <summary>검토 의견 남기기</summary>
        <form
          className="utilization-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget,
              d = new FormData(form);
            if (
              await u.review(
                d.get('state') as ReviewState,
                String(d.get('reason')).trim(),
                String(d.get('limitations')).trim()
              )
            )
              form.reset();
          }}
        >
          <label>
            검토 상태
            <select name="state" defaultValue="NEEDS_EVIDENCE" required>
              <option value="NEEDS_EVIDENCE">추가 근거 필요</option>
              <option value="CANDIDATE">검토 후보</option>
              <option value="NOT_SELECTED">현재 검토 제외</option>
            </select>
          </label>
          <label>
            검토 이유
            <textarea
              name="reason"
              required
              maxLength={2000}
              rows={3}
              placeholder="이 배치를 검토한 근거와 판단"
            />
          </label>
          <label>
            확인이 필요한 현장 조건
            <textarea
              name="limitations"
              required
              maxLength={2000}
              rows={3}
              placeholder="관망 연결, 설치 가능 면적, 관측 검증 등"
            />
          </label>
          <p className="micro-note">
            저장된 의견은 소유자에게도 표시됩니다. 수정은 후속 기록을 추가하는 방식이며
            개인정보·비밀은 적지 마세요.
          </p>
          <button className="primary-button" disabled={u.busy}>
            검토 기록 추가
          </button>
        </form>
      </details>
      <ReviewRecords items={u.reviews.items} />
      {u.reviews.nextCursor && (
        <button className="outline-button" disabled={u.busy} onClick={() => void u.more()}>
          이전 검토 더 보기
        </button>
      )}
      <details>
        <summary>사업 활용 동의 요청</summary>
        <form
          className="utilization-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget,
              d = new FormData(form);
            if (await u.request(String(d.get('title')).trim(), String(d.get('purpose')).trim()))
              form.reset();
          }}
        >
          <p>
            현재 선택한 계산 하나에 대한 요청입니다. 연구 동의가 있어도 사업 목적의 자료 이용은
            소유자의 별도 동의가 필요합니다.
          </p>
          <label>
            요청 제목
            <input
              name="title"
              required
              minLength={2}
              maxLength={100}
              placeholder="예: 성수 빗물관리 후보 배치 검토"
            />
          </label>
          <label>
            활용 목적과 검토 범위
            <textarea
              name="purpose"
              required
              minLength={10}
              maxLength={2000}
              rows={4}
              placeholder="자료를 어떤 검토에 사용할지 구체적으로 작성"
            />
          </label>
          <p className="micro-note">
            요청 후 내용은 바꿀 수 없습니다. 승인 전에는 이 목적의 재현 파일을 내려받을 수 없습니다.
          </p>
          <button className="primary-button" disabled={u.busy}>
            소유자에게 동의 요청
          </button>
        </form>
      </details>
    </section>
  );
}
