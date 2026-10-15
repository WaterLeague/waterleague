import { describe, expect, it } from 'vitest';
import { mapRequest, mapRequestDetail, mapRequestPage, mapReview } from './utilizationMapper';
const request = {
  id: 'f1a75cbf-6d8c-48b6-8f33-11be15df759c',
  jobId: '1e0a0754-188a-42cd-9d94-b9dd109f1881',
  versionId: '02251a48-a597-4b51-b04f-ac10ab246b48',
  modelHash: 'a'.repeat(64),
  organizationId: '1c4ed168-3458-4aa0-bb5f-4ead34be9408',
  organizationName: '시험 기관',
  title: '후보 검토',
  purpose: '관측 자료와 비교할 후보 배치 검토',
  policyVersion: 'APPLICATION_REVIEW_2026_10_V1',
  termsHash: 'b'.repeat(64),
  state: 'GRANTED',
  revision: 2,
  createdAt: '2026-10-16T00:00:00Z',
  updatedAt: '2026-10-16T01:00:00Z',
};
describe('활용 요청과 동의 이력 계약', () => {
  it('다른 내용·결정·버전의 동의 이력 거부', () => {
    const d = {
      decision: 'GRANT',
      revision: 2,
      termsHash: request.termsHash,
      createdAt: request.updatedAt,
    };
    expect(mapRequestDetail({ request, decisions: [d] }).request.state).toBe('GRANTED');
    for (const changes of [{ decision: 'REVOKE' }, { revision: 3 }, { termsHash: 'c'.repeat(64) }])
      expect(() => mapRequestDetail({ request, decisions: [{ ...d, ...changes }] })).toThrow();
    expect(() => mapRequestDetail({ request, decisions: [] })).toThrow();
    expect(() => mapRequest({ ...request, state: 'PENDING' })).toThrow();
    expect(() => mapRequest({ ...request, policyVersion: 'unknown' })).toThrow();
  });
  it('중복 항목과 다른 페이지 커서 거부', () => {
    expect(mapRequestPage({ items: [request], nextCursor: null }).items).toHaveLength(1);
    expect(() => mapRequestPage({ items: [request, request], nextCursor: null })).toThrow();
    expect(() => mapRequestPage({ items: [request], nextCursor: request.id })).toThrow();
  });
  it('검토 의견을 현장 적용 완료 상태로 표시하지 않음', () => {
    const r = {
      id: request.id,
      jobId: request.jobId,
      organizationId: request.organizationId,
      organizationName: '시험 기관',
      state: 'NEEDS_EVIDENCE',
      reason: '배수 자료 확인',
      limitations: '관망 자료 미확보',
      createdAt: request.createdAt,
    };
    expect(mapReview(r).state).toBe('NEEDS_EVIDENCE');
    expect(() => mapReview({ ...r, state: 'APPLIED' })).toThrow();
    expect(() => mapReview({ ...r, limitations: '' })).toThrow();
  });
});
