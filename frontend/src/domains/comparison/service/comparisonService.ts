import type { RainfallComparison } from '../entity/comparison';
export function comparisonState(group: RainfallComparison) {
  if (group.jobs.some((j) => j.state === 'QUEUED' || j.state === 'RUNNING')) return '계산 진행 중';
  if (group.jobs.every((j) => j.state === 'SUCCEEDED')) return '전체 계산 완료';
  return '일부 계산 실패';
}
export const jobStateNames = {
  QUEUED: '대기',
  RUNNING: '계산 중',
  SUCCEEDED: '완료',
  FAILED: '실패',
  REJECTED: '거부',
};
