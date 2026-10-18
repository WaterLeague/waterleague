import type { Budget, BudgetAccounting } from '../dto/budgetDto';
import { facilities, won } from '../../game/service/gameService';
import { BudgetLedgerHistory } from './BudgetLedgerHistory';
export function BudgetEvidence({
  value,
  research = false,
  accounting,
}: {
  value: Budget | null;
  research?: boolean;
  accounting?: BudgetAccounting | null;
}) {
  if (!value) return null;
  const usage = accounting ?? (!research ? value.accounting : null);
  return (
    <>
      {usage && (
        <details className="budget-evidence budget-breakdown">
          <summary>{research ? '내 설계' : '내 설치'} · 시설별 사용액</summary>
          {usage.programs.map((p) => (
            <section key={p.id}>
              <strong>
                {p.name} · 한도 {won(p.limitKrw)}
              </strong>
              <dl>
                {usage.facilities
                  .filter((f) => f.programId === p.id)
                  .map((f) => (
                    <div key={f.facilityType}>
                      <dt>{facilities[f.facilityType].name}</dt>
                      <dd>{won(f.allocatedKrw)}</dd>
                    </div>
                  ))}
              </dl>
              <p>사업 잔액 {won(p.remainingKrw)} · 위 시설이 함께 사용</p>
            </section>
          ))}
        </details>
      )}
      {!research && value.personal && <BudgetLedgerHistory budget={value} />}
      <details className="budget-evidence">
        <summary>{research ? '연구 예산' : '1인당 설치 예산'} · 공개 근거</summary>
        <p>{value.policy.note}</p>
        {research && (
          <p>주간 설치 예산과 별도로 20억 원을 사용하며 여러 구의 연구 배치를 합산합니다.</p>
        )}
        <a href={value.policy.sourceUrl} target="_blank" rel="noreferrer">
          {value.policy.sourceTitle} ↗
        </a>
      </details>
    </>
  );
}
