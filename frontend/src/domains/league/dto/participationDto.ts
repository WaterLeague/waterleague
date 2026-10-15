import { z } from 'zod';
const time = z.iso.datetime({ offset: true });
const state = z.enum(['PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN']);
export const participantDto = z.object({
  leagueId: z.uuid(),
  ownerId: z.uuid(),
  displayName: z.string().max(40),
  state,
  revision: z.number().int().positive(),
  reviewRequired: z.boolean(),
  rulesHash: z.string().regex(/^[a-f0-9]{64}$/),
  createdAt: time,
  updatedAt: time,
});
export const eventDto = z.object({
  revision: z.number().int().positive(),
  state,
  reason: z.string().max(500),
  createdAt: time,
});
export const teamDto = z.object({
  id: z.uuid(),
  name: z.string().min(1).max(60),
  captain: z.boolean(),
  frozenAt: time.nullable(),
  members: z
    .array(
      z.object({
        displayName: z.string().max(40),
        captain: z.boolean(),
        self: z.boolean(),
        eligible: z.boolean(),
      })
    )
    .min(1)
    .max(10),
  submissionCount: z.number().int().min(0).max(100),
  eligible: z.boolean(),
  invitationActive: z.boolean(),
});
export const participationDto = z.object({
  participant: participantDto.nullable(),
  events: z.array(eventDto).max(100),
  team: teamDto.nullable(),
  submissionCount: z.number().int().min(0).max(100),
});
export const summaryDto = z.object({
  leagueId: z.uuid(),
  title: z.string().max(100),
  organizationName: z.string().max(100),
  access: z.enum(['PUBLIC', 'INVITE']),
  state,
  updatedAt: time,
});
export const participantPageDto = z.object({
  items: z.array(participantDto).max(100),
  nextCursor: z.uuid().nullable(),
});
export const teamPreviewDto = z.object({
  id: z.uuid(),
  name: z.string().max(60),
  memberCount: z.number().int().min(1).max(10),
  teamSizeLimit: z.number().int().min(2).max(10),
  rulesHash: z.string().regex(/^[a-f0-9]{64}$/),
});
export const invitationDto = z.object({
  code: z.string().regex(/^[A-Za-z0-9_-]{43}$/),
  expiresAt: time,
});
export const invitationStatusDto = z.object({ active: z.boolean(), expiresAt: time });
export const teamCreatedDto = z.object({
  team: teamDto,
  code: z.string().regex(/^[A-Za-z0-9_-]{43}$/),
});
