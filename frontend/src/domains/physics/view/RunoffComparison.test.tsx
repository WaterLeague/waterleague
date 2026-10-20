import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/publicRunoffComparison.json';
import { runoffComparisonDto } from '../dto/runoffComparisonDto';
import { RunoffComparison } from './RunoffComparison';
import native from './fixtures/nativeDesignContract.json';
import { designContractDto } from '../dto/designContractDto';

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

it('원형 실행의 평가 표면과 시설 직접 강우 면적을 같은 비교 안에 표시', () => {
  expect(designContractDto.safeParse(native.contract).success).toBe(true);
  const html = renderToStaticMarkup(
    <RunoffComparison value={native.comparison} contract={native.contract} />
  );
  expect(html).toContain('평가 표면');
  expect(html).toContain('시설 설치 10 m²');
  expect(html).toContain('시설에 직접 내리는 강우만 유입');
  expect(html).not.toContain('범위 근거를 확인하지 못했습니다');
});

it('다른 평가 시각·단위·과대 면적·비용 결측의 모순을 정상 근거로 표시하지 않음', () => {
  const original = native.contract;
  const malformed = [
    { ...original, units: { ...original.units, coordinate: 'degree' } },
    {
      ...original,
      facility: { ...original.facility, areaM2: original.spatial.evaluationSurfaceAreaM2 + 1 },
    },
    { ...original, cost: { ...original.cost, status: 'NOT_RECORDED' } },
  ];
  for (const contract of malformed)
    expect(designContractDto.safeParse(contract).success).toBe(false);
  const changedWindow = {
    ...original,
    evaluation: { ...original.evaluation, start: '2022-08-08T09:03:17+00:00' },
  };
  for (const contract of [...malformed, changedWindow]) {
    const html = renderToStaticMarkup(
      <RunoffComparison value={native.comparison} contract={contract} />
    );
    expect(html).toContain('설계·평가 범위 근거를 확인하지 못했습니다');
    expect(html).not.toContain('시설에 직접 내리는 강우만 유입');
  }
});
