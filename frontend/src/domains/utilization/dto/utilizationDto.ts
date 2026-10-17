import { z } from 'zod';
const time = z.iso.datetime({ offset: true });
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const requestDto = z
  .object({
    id: z.uuid(),
    jobId: z.uuid(),
    versionId: z.uuid(),
    modelHash: hash,
    organizationId: z.uuid(),
    organizationName: z.string().min(1).max(100),
    title: z.string().min(2).max(100),
    purpose: z.string().min(10).max(2000),
    policyVersion: z.literal('APPLICATION_REVIEW_2026_10_V1'),
    termsHash: hash,
    state: z.enum(['PENDING', 'GRANTED', 'DECLINED', 'REVOKED']),
    revision: z.number().int().min(1).max(3),
    createdAt: time,
    updatedAt: time,
  })
  .refine((r) => r.revision === { PENDING: 1, GRANTED: 2, DECLINED: 2, REVOKED: 3 }[r.state]);
export const requestDetailDto = z.object({
  request: requestDto,
  decisions: z
    .array(
      z.object({
        decision: z.enum(['GRANT', 'DECLINE', 'REVOKE']),
        revision: z.number().int().min(2).max(3),
        termsHash: hash,
        createdAt: time,
      })
    )
    .max(2),
});
export const reviewDto = z.object({
  id: z.uuid(),
  jobId: z.uuid(),
  organizationId: z.uuid(),
  organizationName: z.string().min(1).max(100),
  state: z.enum(['CANDIDATE', 'NEEDS_EVIDENCE', 'NOT_SELECTED']),
  reason: z.string().min(1).max(2000),
  limitations: z.string().min(1).max(2000),
  createdAt: time,
});
export const requestPageDto = z.object({
  items: requestDto.array().max(50),
  nextCursor: z.uuid().nullable(),
});
export const reviewPageDto = z.object({
  items: reviewDto.array().max(50),
  nextCursor: z.uuid().nullable(),
});
