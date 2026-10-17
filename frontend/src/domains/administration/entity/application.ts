import type { MemberType } from '../../account/entity/account';
export interface MemberApplication {
  id: string;
  username: string;
  displayName: string;
  memberType: MemberType;
  approvalStatus: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUSPENDED';
  enabled: boolean;
  organizationId: string | null;
  organizationName: string;
  purpose: string;
  createdAt: string;
}
export interface Review {
  decision: string;
  reason: string;
  reviewedAt: string;
}
