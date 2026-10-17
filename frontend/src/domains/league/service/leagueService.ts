import type { League, OwnSubmission } from '../entity/league';
import type { Job, Lab, Placement, FacilityType } from '../../game/entity/game';
import type { LeagueRules } from '../entity/league';
export function availableLimits(lab: Lab, types: FacilityType[]) {
  const cells = lab.model.cells.filter((c) => c.allowedTypes.some((t) => types.includes(t)));
  return {
    placementLimit: Math.min(lab.model.maxPlacements, cells.length),
    areaLimitM2: cells.reduce((sum, c) => sum + Math.round(c.maxAreaM2 * 100), 0) / 100,
  };
}
export function totalArea(placements: Placement[]) {
  return placements.reduce((sum, p) => sum + Math.round(p.areaM2 * 100), 0) / 100;
}
export function exceedsLeagueLimits(
  placements: Placement[],
  rules: Pick<LeagueRules, 'placementLimit' | 'areaLimitM2'>
) {
  return (
    (rules.placementLimit != null && placements.length > rules.placementLimit) ||
    (rules.areaLimitM2 != null &&
      Math.round(totalArea(placements) * 100) > Math.round(rules.areaLimitM2 * 100))
  );
}
export const phaseNames = {
  DRAFT: '비공개 초안',
  SCHEDULED: '접수 예정',
  OPEN: '접수 중',
  CLOSED: '접수 마감',
  CANCELLED: '취소',
};
export const leagueTime = (value: string) =>
  new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
export function eligibleJobs(
  league: Pick<League, 'publishedAt'> & { rules: Pick<LeagueRules, 'modelHash'> },
  jobs: Job[],
  submitted: Pick<OwnSubmission, 'jobId'>[] = []
) {
  const submittedIds = new Set(submitted.map((s) => s.jobId));
  return jobs.filter(
    (j) =>
      !submittedIds.has(j.id) &&
      j.state === 'SUCCEEDED' &&
      j.modelHash === league.rules.modelHash &&
      league.publishedAt !== null &&
      Date.parse(j.createdAt) >= Date.parse(league.publishedAt)
  );
}
export function localDateTime(value: string) {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
