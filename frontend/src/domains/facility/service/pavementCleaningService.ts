import catalog from '../../../../../data/derived/pavement-cleaning-v1.json';
import { pavementCleaningDto, type CleaningPair } from '../dto/pavementCleaningDto';

const parsed = pavementCleaningDto.safeParse(catalog);
export const cleaningObservations = parsed.success ? parsed.data : null;
export type InfiltrationUnit = 'mm/min' | 'mm/h';
export const cleaningMethods: Record<CleaningPair['method'], string> = {
  REGENERATIVE_AIR: '공기 순환식 청소차',
  VACUUM_TRUCK: '진공 흡입차',
  VACUUM_TRUCK_WITH_JOINT_STONE_REPLACEMENT: '진공 흡입차·줄눈 골재 보충',
};

export function cleaningComparison(pair: CleaningPair, unit: InfiltrationUnit) {
  const multiplier = unit === 'mm/h' ? 60 : 1;
  const convert = (v: CleaningPair['before']) => ({
    testCount: v.testCount,
    min: v.min * multiplier,
    max: v.max * multiplier,
    mean: v.mean * multiplier,
    median: v.median * multiplier,
    standardDeviation: v.standardDeviation * multiplier,
  });
  const difference = pair.after.median - pair.before.median;
  return {
    before: convert(pair.before),
    after: convert(pair.after),
    medianDifference: difference * multiplier,
    // 신설 상태가 없으므로 청소 전 중앙값 대비 변화만 계산한다.
    medianChangePercent: pair.before.median === 0 ? null : (difference / pair.before.median) * 100,
  };
}
