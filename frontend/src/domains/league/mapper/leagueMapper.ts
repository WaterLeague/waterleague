import { leagueDto } from '../dto/leagueDto';
import { LeagueDataError } from '../exception/LeagueDataError';
import type { League } from '../entity/league';
export function mapLeague(value: unknown): League {
  const p = leagueDto.safeParse(value);
  if (!p.success) throw new LeagueDataError();
  const l = p.data;
  const r = l.rules;
  if (r.schemaVersion >= 2 && (!r.placementLimit || !r.areaLimitM2 || !r.award))
    throw new LeagueDataError();
  if (
    (r.schemaVersion === 3 && !r.participation) ||
    (r.schemaVersion < 3 && r.participation) ||
    (r.participation &&
      (r.participation.entryMode === 'TEAM') !== (r.participation.teamSizeLimit !== null))
  )
    throw new LeagueDataError();
  if (
    r.award &&
    ((r.award.prizeKrw === 0 && r.award.winnerCount !== 0) ||
      (r.award.prizeKrw > 0 && (r.award.winnerCount < 1 || r.award.notice.trim().length < 10)))
  )
    throw new LeagueDataError();
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
