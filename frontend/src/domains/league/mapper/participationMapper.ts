import type { z } from 'zod';
import { LeagueDataError } from '../exception/LeagueDataError';
import { participationDto, participantPageDto } from '../dto/participationDto';
export function parseParticipationData<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) throw new LeagueDataError();
  return result.data;
}
export function mapParticipation(value: unknown, leagueId: string, ownerId: string) {
  const p = parseParticipationData(participationDto, value);
  if (p.participant && (p.participant.leagueId !== leagueId || p.participant.ownerId !== ownerId))
    throw new LeagueDataError();
  if (
    p.team &&
    (!p.participant ||
      p.team.submissionCount !== p.submissionCount ||
      p.team.members.filter((m) => m.self).length !== 1 ||
      p.team.members.filter((m) => m.captain).length !== 1)
  )
    throw new LeagueDataError();
  return p;
}
export function mapParticipantPage(value: unknown, leagueId: string) {
  const page = parseParticipationData(participantPageDto, value);
  if (
    page.items.some((p) => p.leagueId !== leagueId) ||
    new Set(page.items.map((p) => p.ownerId)).size !== page.items.length
  )
    throw new LeagueDataError();
  return page;
}
