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
      <summary>{research ? '연구 예산' : '1인당 설치 예산'} · 공개 근거</summary>
      <p>{value.policy.note}</p>
      {research && (
        <p>주간 설치 예산과 별도로 20억 원을 사용하며 여러 구의 연구 배치를 합산합니다.</p>
      )}
      <a href={value.policy.sourceUrl} target="_blank" rel="noreferrer">
        {value.policy.sourceTitle} ↗
      </a>
    </details>
  );
}
