export type MemberType = 'PLAYER' | 'BUSINESS' | 'INSTITUTION' | 'GOVERNMENT';
export interface Account {
  id: string;
  username: string;
  displayName: string;
  role: 'MEMBER' | 'ADMIN';
  memberType: MemberType | null;
  approvalStatus: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUSPENDED';
  organizationId: string | null;
}
export const memberTypeNames: Record<MemberType, string> = {
  PLAYER: '플레이어',
  BUSINESS: '기업',
  INSTITUTION: '기관',
  GOVERNMENT: '정부',
};
export const isOrganizationMember = (a: Account | null) =>
  !!a &&
  a.role === 'MEMBER' &&
  a.memberType !== null &&
  a.memberType !== 'PLAYER' &&
  a.approvalStatus === 'APPROVED';
