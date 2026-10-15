import {
  requestDto,
  requestDetailDto,
  requestPageDto,
  reviewDto,
  reviewPageDto,
} from '../dto/utilizationDto';
import { UtilizationDataError } from '../exception/UtilizationDataError';
import type {
  CursorPage,
  RequestDetail,
  StrategyReview,
  UtilizationRequest,
} from '../entity/utilization';
function requirePage<T extends { id: string }>(p: CursorPage<T>): CursorPage<T> {
  if (
    new Set(p.items.map((v) => v.id)).size !== p.items.length ||
    (p.nextCursor !== null && (p.items.length !== 50 || p.nextCursor !== p.items.at(-1)?.id))
  )
    throw new UtilizationDataError();
  return p;
}
export function mapRequest(input: unknown): UtilizationRequest {
  const p = requestDto.safeParse(input);
  if (!p.success) throw new UtilizationDataError();
  return p.data;
}
export function mapRequestPage(input: unknown): CursorPage<UtilizationRequest> {
  const p = requestPageDto.safeParse(input);
  if (!p.success) throw new UtilizationDataError();
  return requirePage(p.data);
}
export function mapReview(input: unknown): StrategyReview {
  const p = reviewDto.safeParse(input);
  if (!p.success) throw new UtilizationDataError();
  return p.data;
}
export function mapReviewPage(input: unknown): CursorPage<StrategyReview> {
  const p = reviewPageDto.safeParse(input);
  if (!p.success) throw new UtilizationDataError();
  return requirePage(p.data);
}
export function mapRequestDetail(input: unknown): RequestDetail {
  const p = requestDetailDto.safeParse(input);
  if (!p.success) throw new UtilizationDataError();
  const { request: r, decisions } = p.data;
  const expected = {
    PENDING: [],
    GRANTED: ['GRANT'],
    DECLINED: ['DECLINE'],
    REVOKED: ['GRANT', 'REVOKE'],
  }[r.state];
  if (
    decisions.length !== expected.length ||
    decisions.some(
      (d, i) => d.decision !== expected[i] || d.revision !== i + 2 || d.termsHash !== r.termsHash
    )
  )
    throw new UtilizationDataError();
  return p.data;
}
