import { leagueDto } from '../dto/leagueDto';
import { LeagueDataError } from '../exception/LeagueDataError';
import type { League } from '../entity/league';
export function mapLeague(value: unknown): League {
  const p = leagueDto.safeParse(value);
  if (!p.success) throw new LeagueDataError();
  const l = p.data;
  if (
    Date.parse(l.rules.closesAt) <= Date.parse(l.rules.opensAt) ||
    new Set(l.rules.allowedTypes).size !== l.rules.allowedTypes.length ||
    (l.state !== 'DRAFT' && !l.publishedAt)
  )
    throw new LeagueDataError();
  return l;
}
export function mapLeagues(value: unknown): League[] {
  if (!Array.isArray(value) || value.length > 100) throw new LeagueDataError();
  return value.map(mapLeague);
}
