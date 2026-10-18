import type { BudgetRecordEvidence as Evidence } from '../dto/budgetDto';
import { won } from '../../game/service/gameService';
import './budget-record.css';

const at = (value: string) =>
  new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

export function BudgetRecordEvidence({ value }: { value?: Evidence | null }) {
  if (!value || value.status === 'NOT_RECORDED')
    return (
      <section className="budget-record-evidence" aria-label="이 설치의 예산 원장">
        <h4>설치·취소 원장 미확보</h4>
        <p>
          표시된 설치비 외에 배정·취소 원장 근거가 없습니다. 배정액을 0원으로 처리하지 않습니다.
        </p>
      </section>
    );
  const allocation = value.entries.find((entry) => entry.eventType === 'ALLOCATE');
  return (
    <section className="budget-record-evidence" aria-label="이 설치의 예산 원장">
      <h4>이 설치의 예산 배정·취소</h4>
      <dl className="budget-record-values">
        <div>
          <dt>계산 종료 당시 배정액</dt>
          <dd>{won(value.allocatedAtEvaluationKrw!)}</dd>
          <small>{at(value.evaluatedThrough)} KST</small>
        </div>
        <div>
          <dt>원장 조회 시점 배정액</dt>
          <dd>{won(value.allocatedAtCaptureKrw!)}</dd>
          <small>{at(value.capturedAt)} KST</small>
        </div>
      </dl>
      <p>
        선택한 설치 한 건의 기록입니다. 취소는 게임 설계 배정의 해제이며 실제 공사비 환급이
        아닙니다.
      </p>
      <ol className="budget-record-events">
        {value.entries.map((entry) => (
          <li key={entry.id}>
            <div>
              <strong>{entry.eventType === 'ALLOCATE' ? '설치 배정' : '설계 취소'}</strong>
              <time dateTime={entry.effectiveAt}>{at(entry.effectiveAt)} KST</time>
              {Date.parse(entry.effectiveAt) > Date.parse(value.evaluatedThrough) && (
                <small className="budget-event-later">계산 종료 이후</small>
              )}
              {entry.provenance === 'LEGACY_IMPORT' && <small>이전 설치 기록에서 이관</small>}
            </div>
            <span>
              {entry.eventType === 'ALLOCATE' ? '배정' : '해제'} {won(entry.amountKrw)}
            </span>
          </li>
        ))}
      </ol>
      <p>
        기록의 실제 발생 시각으로 당시 배정액을 복원했습니다. 계산 완료 후 발생한 취소는 당시 금액에
        반영하지 않습니다.
      </p>
      <details>
        <summary>최초 배정의 예산 정책</summary>
        <p>
          설치 원가 {won(value.installationCostKrw)} · {allocation?.accountingVersion}
        </p>
        {allocation?.sourceBudgetPolicy != null ? (
          <pre>{JSON.stringify(allocation.sourceBudgetPolicy, null, 2)}</pre>
        ) : (
          <p>이전 기록에 예산 정책 원문이 없습니다. 현재 정책으로 대체하지 않습니다.</p>
        )}
      </details>
    </section>
  );
}
