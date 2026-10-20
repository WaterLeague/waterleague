import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/publicRunoffComparison.json';
import { runoffComparisonDto } from '../dto/runoffComparisonDto';
import { RunoffComparison } from './RunoffComparison';
import native from './fixtures/nativeDesignContract.json';
import { designContractDto } from '../dto/designContractDto';
import timingFixture from './fixtures/runoffTiming.json';

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

it('7종의 실제 관측 계산에서 지연과 무유출을 구별하고 이전 기록은 미수집으로 표시', () => {
  expect(timingFixture.classification).toBe('PUBLIC_OBSERVED_NATIVE_SURFACES_NOT_FIELD_VALIDATION');
  expect(timingFixture.cases).toHaveLength(7);
  for (const row of timingFixture.cases) {
    const value = runoffComparisonDto.parse(row.comparison);
    const html = renderToStaticMarkup(<RunoffComparison value={value} contract={row.contract} />);
    expect(html).toContain('지연 시간은 체적 점수에 더하지 않습니다');
    expect(html).not.toContain('근거를 확인하지 못했습니다');
    expect(html).toContain(
      value.detention!.status === 'COMPARABLE'
        ? '유출량 중심시각 지연'
        : '배출량이 0이므로 중심시각 지연을 산정하지 않습니다'
    );
  }
  const html = renderToStaticMarkup(<RunoffComparison value={native.comparison} />);
  expect(html).toContain('이전 기록에는 유출량 중심시각이 수집되지 않았습니다');
});

it('지연 값·모멘트·평가 창·점수 자격·버전 누락과 변조를 거부', () => {
  const original = runoffComparisonDto.parse(
    timingFixture.cases.find((c) => c.facilityType === 'GREEN_ROOF')!.comparison
  );
  const bad = [
    { ...original, detention: undefined },
    { ...original, metricComparison: undefined },
    { ...original, schemaVersion: 2 },
    {
      ...original,
      detention: {
        ...original.detention,
        centroidDelaySeconds: -original.detention!.centroidDelaySeconds!,
      },
    },
    { ...original, detention: { ...original.detention, evaluationWindowOnly: false } },
    { ...original, detention: { ...original.detention, rankingEligible: true } },
    {
      ...original,
      cases: original.cases.map((c) => ({ ...c, metrics: { ...c.metrics, timing: undefined } })),
    },
    {
      ...original,
      cases: original.cases.map((c) => ({
        ...c,
        metrics: {
          ...c.metrics,
          timing: {
            ...c.metrics.timing,
            firstMomentM3Seconds: c.metrics.timing!.firstMomentM3Seconds + 1000,
          },
        },
      })),
    },
    {
      ...original,
      cases: original.cases.map((c) => ({
        ...c,
        metrics: {
          ...c.metrics,
          timing: { ...c.metrics.timing, centroidSeconds: c.metrics.observedSeconds + 1 },
        },
      })),
    },
  ];
  for (const value of bad) {
    expect(runoffComparisonDto.safeParse(value).success).toBe(false);
    expect(renderToStaticMarkup(<RunoffComparison value={value} />)).toContain(
      '유출 비교 자료를 확인하지 못했습니다'
    );
  }
});

it('음의 내부 수치값은 양의 총배출에도 지연 비교를 보류하며 원값을 지우지 않음', () => {
  const value = runoffComparisonDto.parse(
    timingFixture.cases.find((c) => c.facilityType === 'GREEN_ROOF')!.comparison
  );
  value.cases[0].metrics.minimumComponentRateM3s = -1e-18;
  value.cases[0].metrics.timing = {
    ...value.cases[0].metrics.timing!,
    status: 'WITHHELD',
    reason: 'NEGATIVE_COMPONENT_RATE',
    centroidSeconds: null,
  };
  value.detention = {
    ...value.detention!,
    status: 'WITHHELD',
    reason: 'BASELINE_NEGATIVE_COMPONENT_RATE',
    centroidDelaySeconds: null,
  };
  expect(runoffComparisonDto.safeParse(value).success).toBe(true);
  const html = renderToStaticMarkup(<RunoffComparison value={value} />);
  expect(html).toContain('내부 유량에 음의 수치값이 있어 배출 시각 비교를 보류합니다');
  expect(value.cases[0].metrics.timing.firstMomentM3Seconds).toBeGreaterThan(0);
  value.detention.centroidDelaySeconds = 0;
  expect(runoffComparisonDto.safeParse(value).success).toBe(false);
});
