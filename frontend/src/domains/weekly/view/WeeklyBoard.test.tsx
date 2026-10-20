import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from '../../physics/view/fixtures/score-policy-weekly-http-v1.json';
import { weeklyDto } from '../dto/weeklyDto';
import { WeeklyBoard } from './WeeklyBoard';
function mixed() {
  const value = weeklyDto.parse(fixture.value);
  const period = value.current;
  period.status = 'WITHHELD';
  period.comparisonStatus = 'WITHHELD';
  period.comparisonReason = 'MIXED_COMPARISON_CONTEXTS';
  period.comparisonGroupHash = null;
  for (const row of [...period.districts, ...period.players, ...(period.own ? [period.own] : [])]) {
    row.scoreM3 = null;
    row.scoreM3Exact = null;
    row.rank = null;
  }
  period.winnerDistrictIds = [];
  return value;
}
it('실제 HTTP 원문과 평가 조건·정확한 원장 문자열 결속', () => {
  const value = weeklyDto.parse(fixture.value);
  expect(value.scorePolicy.weeklyDecimalPlaces).toBe(9);
  expect(value.current.comparisonStatus).toBe('COMPARABLE');
  expect(
    value.current.players
      .filter((p) => p.scoreM3 !== null)
      .every((p) => Number(p.scoreM3Exact) === p.scoreM3)
  ).toBe(true);
});
it('조건이 섞인 기록은 평가 초를 보존하면서 합산·순위·우승 보류', () => {
  const value = weeklyDto.parse(mixed());
  expect(value.current.evaluatedSeconds).toBeGreaterThan(0);
  const html = renderToStaticMarkup(
    <WeeklyBoard value={value} error="" ownDistrictId={null} onDistrict={() => {}} />
  );
  expect(html).toContain('평가 조건 확인 · 순위 보류');
  expect(html).toContain('합산 보류');
  expect(html).not.toContain('>0<');
  value.current.districts[0].scoreM3 = 0;
  value.current.districts[0].scoreM3Exact = '0.000000000';
  value.current.districts[0].rank = 1;
  expect(weeklyDto.safeParse(value).success).toBe(false);
});
it('보류 사유·비교 집단·동점 규칙·저장값 변조 거부', () => {
  const value = mixed();
  value.current.comparisonReason = null;
  expect(weeklyDto.safeParse(value).success).toBe(false);
  const changed = structuredClone(fixture.value);
  changed.scorePolicy.relativeUsedForRanking = true as false;
  expect(weeklyDto.safeParse(changed).success).toBe(false);
});
