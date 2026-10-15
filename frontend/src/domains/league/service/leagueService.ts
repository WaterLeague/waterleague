import type { League } from '../entity/league';
import type { Job } from '../../game/entity/game';
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
export function eligibleJobs(league: League, jobs: Job[]) {
  return jobs.filter(
    (j) =>
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
