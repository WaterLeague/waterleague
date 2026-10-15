import type { MemberApplication } from '../entity/application';
export const approvalNames = {
  PENDING: '승인 대기',
  APPROVED: '승인',
  REJECTED: '반려',
  SUSPENDED: '이용 정지',
};
export function decisionsFor(member: MemberApplication) {
  if (!member.enabled) return [];
  return member.approvalStatus === 'PENDING'
    ? ['APPROVE', 'REJECT']
    : member.approvalStatus === 'APPROVED'
      ? ['SUSPEND']
      : ['APPROVE'];
}
export const decisionNames: Record<string, string> = {
  APPROVE: '승인',
  REJECT: '반려',
  SUSPEND: '이용 정지',
};
