export type RequestState = 'PENDING' | 'GRANTED' | 'DECLINED' | 'REVOKED';
export type Decision = 'GRANT' | 'DECLINE' | 'REVOKE';
export type ReviewState = 'CANDIDATE' | 'NEEDS_EVIDENCE' | 'NOT_SELECTED';
export interface UtilizationRequest {
  id: string;
  jobId: string;
  versionId: string;
  modelHash: string;
  organizationId: string;
  organizationName: string;
  title: string;
  purpose: string;
  policyVersion: 'APPLICATION_REVIEW_2026_10_V1';
  termsHash: string;
  state: RequestState;
  revision: number;
  createdAt: string;
  updatedAt: string;
}
export interface RequestDetail {
  request: UtilizationRequest;
  decisions: { decision: Decision; revision: number; termsHash: string; createdAt: string }[];
}
export interface StrategyReview {
  id: string;
  jobId: string;
  organizationId: string;
  organizationName: string;
  state: ReviewState;
  reason: string;
  limitations: string;
  createdAt: string;
}
export interface CursorPage<T> {
  items: T[];
  nextCursor: string | null;
}
