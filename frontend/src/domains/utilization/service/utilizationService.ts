import type { Decision, RequestState, ReviewState } from '../entity/utilization';
export const stateLabels: Record<RequestState, string> = {
  PENDING: '동의 대기',
  GRANTED: '동의함',
  DECLINED: '거절함',
  REVOKED: '철회함',
};
export const decisionLabels: Record<Decision, string> = {
  GRANT: '이용 동의',
  DECLINE: '요청 거절',
  REVOKE: '동의 철회',
};
export const reviewLabels: Record<ReviewState, string> = {
  CANDIDATE: '검토 후보',
  NEEDS_EVIDENCE: '추가 근거 필요',
  NOT_SELECTED: '현재 검토 제외',
};
export const displayTime = (value: string) => new Date(value).toLocaleString('ko-KR');
