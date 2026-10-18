import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/publicRunoffComparison.json';
import { runoffComparisonDto } from '../dto/runoffComparisonDto';
import { RunoffComparison } from './RunoffComparison';

it('공개 강우의 선행 제외·배수 포함 첨두와 음의 저감량 표시', () => {
  for (const c of fixture.cases)
    expect(runoffComparisonDto.safeParse(c.comparison).success).toBe(true);
  const html = renderToStaticMarkup(<RunoffComparison value={fixture.cases[1].comparison} />);
  expect(html).toContain('-0.083208');
  expect(html).toContain('-0.20411');
  expect(html).toContain('21,540');
  expect(html).toContain('2022. 8. 8. 21:16:00');
  expect(html).toContain('하수관·하천이나 구 전체의 첨두가 아닙니다');
  expect(html).toContain('남은 물을 영구 저감으로');
});

it('선행 첨두·중복 조건·저류 누락·변화 부호의 불일치 거부', () => {
  const original = fixture.cases[1].comparison;
  const bad = [
    { ...original, peakReductionM3s: -original.peakReductionM3s },
    { ...original, cases: [original.cases[0], original.cases[0]] },
    {
      ...original,
      cases: original.cases.map((c) => ({ ...c, accountedDischargeM3: c.dischargeM3 })),
    },
    {
      ...original,
      cases: original.cases.map((c) => ({
        ...c,
        metrics: { ...c.metrics, peakAt: c.metrics.start },
      })),
    },
  ];
  for (const value of bad) {
    expect(runoffComparisonDto.safeParse(value).success).toBe(false);
    const html = renderToStaticMarkup(<RunoffComparison value={value} />);
    expect(html).toContain('유출 비교 자료를 확인하지 못했습니다');
    expect(html).not.toContain('m³/s');
  }
});
