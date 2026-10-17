import type { Budget } from '../dto/budgetDto';
export function BudgetEvidence({
  value,
  research = false,
}: {
  value: Budget | null;
  research?: boolean;
}) {
  if (!value) return null;
  return (
    <details className="budget-evidence">
      <summary>{research ? '연구 예산' : '구별 공동 배치예산'} · 공개 근거</summary>
      <p>{value.policy.note}</p>
      {research && <p>선택 구마다 공동 잔액을 쓰지 않는 8천만 원의 독립 연구 설계 한도입니다.</p>}
      <a href={value.policy.sourceUrl} target="_blank" rel="noreferrer">
        {value.policy.sourceTitle} ↗
      </a>
    </details>
  );
}
