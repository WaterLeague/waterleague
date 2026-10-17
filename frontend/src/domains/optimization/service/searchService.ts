import type { SearchArm, SearchInput, ResearchSearch, SearchSummary } from '../entity/search';
export const searchArmNames: Record<SearchArm, string> = {
  PATTERN: '패턴 기반 후보',
  UNIFORM: '균등 무작위 대조',
};
export function searchFingerprint(input: SearchInput) {
  return JSON.stringify([
    [...input.jobIds].sort(),
    input.settings.topK,
    input.settings.budgetKrw,
    input.settings.seed,
    input.settings.candidatesPerArm,
  ]);
}
export function searchState(d: Pick<SearchSummary, 'completeComparison' | 'arms'>) {
  if (d.completeComparison) return '모든 후보 계산 완료';
  const active = d.arms.reduce((n, a) => n + a.queued + a.running, 0),
    failed = d.arms.reduce((n, a) => n + a.failed + a.rejected, 0);
  return active
    ? `${active}개 계산 대기·실행 중${failed ? ` · ${failed}개 실패` : ''}`
    : `${failed}개 실패 · 불완전 비교`;
}
export function searchActive(d: ResearchSearch | null) {
  return !!d?.candidates.some((c) => c.state === 'QUEUED' || c.state === 'RUNNING');
}
export function searchInputError(input: SearchInput, budget: number, sourceCosts: number[]) {
  const s = input.settings;
  if (input.jobIds.length < 2 || input.jobIds.length > 50)
    return '서로 다른 배치의 제출 기록을 2개 이상 선택해 주세요.';
  if (!Number.isInteger(s.budgetKrw) || s.budgetKrw < 1 || s.budgetKrw > budget)
    return '예산을 모델 한도 이내의 정수 원으로 입력해 주세요.';
  if (sourceCosts.some((c) => c > s.budgetKrw))
    return '비교 예산은 선택한 모든 원본의 비용 이상이어야 합니다.';
  if (!Number.isInteger(s.seed) || s.seed < 0 || s.seed > 2147483647)
    return '시드를 0~2,147,483,647의 정수로 입력해 주세요.';
  if (
    !Number.isInteger(s.topK) ||
    s.topK < 2 ||
    s.topK > 20 ||
    !Number.isInteger(s.candidatesPerArm) ||
    s.candidatesPerArm < 1 ||
    s.candidatesPerArm > 4
  )
    return '상위 기준과 방법당 후보 수를 확인해 주세요.';
  return '';
}
