import type { WeeklySnapshot } from '../dto/weeklyDto';
import { scoreFormat } from './scoreFormat';

export function districtScoreLabel(
  district: WeeklySnapshot['current']['districts'][number] | undefined,
  withheld: boolean,
  includeRank = true
) {
  if (!district) return '점수 조회 중';
  if (district.scoreM3 === null)
    return withheld && (district.evaluatedSeconds ?? district.evaluatedMinutes * 60) > 0
      ? '합산 보류'
      : '점수 없음';
  return `${includeRank && district.rank ? `${district.rank}위 · ` : ''}총 점수 ${scoreFormat.format(district.scoreM3)} m³`;
}
