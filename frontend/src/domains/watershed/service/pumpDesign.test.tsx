import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import source from '../view/fixtures/catalog.json';
import actual from '../view/fixtures/public-pump-job.json';
import { watershedCatalogDto, watershedJobDto } from '../dto/watershedDto';
import { pumpOperationDto, type PumpPlacement } from '../dto/pumpDto';
import type { StoragePlacement } from '../dto/storageDto';
import { validateCombinedDesign } from './storageDesign';
import { WatershedResult } from '../view/WatershedResult';
import { pumpReceivers } from './pumpDesign';

const catalog = watershedCatalogDto.parse(source);
const tank: StoragePlacement = {
  id: 'Tank',
  connectionId: 'C1',
  areaM2: 100,
  invertM: 12,
  depthM: 9,
  initialDepthM: 0,
  inlet: { crestM: 18.5, diameterM: 0.2, dischargeCoefficient: 0.65, flapGate: false },
  drain: { crestM: 16.2, diameterM: 0.03, dischargeCoefficient: 0.65, flapGate: false },
  overflow: { crestM: 18.5, diameterM: 0.12, dischargeCoefficient: 0.65, flapGate: false },
};
const pump: PumpPlacement = {
  id: 'Pump1',
  fromNode: 'WLST_Tank',
  toNode: 'J2',
  startDepthM: 1.8,
  stopDepthM: 1.2,
  initialStatus: 'OFF',
  delivery: {
    lengthM: 10,
    diameterM: 0.5,
    roughnessMm: 0.1,
    pressureHeadLimitM: 20,
    entranceLoss: 0.5,
    exitLoss: 1,
    averageLoss: 0,
    checkValve: true,
  },
};
it('저류조 흡입과 하류 연결·삭제된 시설·중복·공유 식별자 검증', () => {
  expect(validateCombinedDesign(catalog, [], [tank], [], [pump])).toBe('');
  expect(pumpReceivers(catalog, [tank], 'WLST_Tank').some((n) => n.id === 'J1')).toBe(false);
  expect(validateCombinedDesign(catalog, [], [], [], [pump])).not.toBe('');
  for (const changed of [
    { ...pump, fromNode: 'NEW' },
    { ...pump, toNode: 'Out1' },
    { ...pump, fromNode: 'J2', toNode: 'J1' },
    { ...pump, id: 'tank' },
    { ...pump, stopDepthM: 1.8 },
    { ...pump, startDepthM: 9.001 },
    { ...pump, delivery: { ...pump.delivery, roughnessMm: 0 } },
    { ...pump, delivery: { ...pump.delivery, pressureHeadLimitM: 0.5 } },
  ])
    expect(validateCombinedDesign(catalog, [], [tank], [], [changed])).not.toBe('');
  expect(
    validateCombinedDesign(catalog, [], [tank], [], [pump, { ...pump, id: 'Pump2' }])
  ).not.toBe('');
});
it('실제 워커의 펌프 운전·내부 이송·외부 악화와 미산정 비용 표시', () => {
  const job = watershedJobDto.parse(actual);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('펌프 운전 결과');
  expect(html).toContain('191.19');
  expect(html).toContain('기동 3회');
  expect(html).toContain('125.47 m³ 감소');
  expect(html).toContain('0.0754 m³ 증가');
  expect(html).toContain('전기 사용량 미산정');
  expect(html).toContain('공사비 미산정');
  expect(html).not.toContain('0원');
});
it('누락·타 펌프 기록과 토출부 월류 변조를 정상 결과로 표시하지 않음', () => {
  const missing = structuredClone(actual);
  missing.result.cases[1].pumpOperation.pumps = [];
  expect(watershedJobDto.safeParse(missing).success).toBe(false);
  const wrong = structuredClone(actual);
  wrong.result.cases[1].pumpOperation.pumps[0].linkId = 'WLPU_Other';
  expect(watershedJobDto.safeParse(wrong).success).toBe(false);
  const changed = structuredClone(actual);
  changed.result.cases[1].pumpOperation.pumps[0].deliveryFloodingM3 = 10;
  expect(watershedJobDto.safeParse(changed).success).toBe(false);
  const report = pumpOperationDto.parse(actual.result.cases[1].pumpOperation);
  report.pumps.push({ ...report.pumps[0] });
  expect(pumpOperationDto.safeParse(report).success).toBe(false);
});
it('곡선 밖 운전은 실패·에너지 보류로 보존하며 성공 판정 위조 거부', () => {
  const invalid = structuredClone(actual);
  invalid.result.cases[1].pumpOperation.pumps[0].outsideHeadCurveSeconds = 1;
  expect(watershedJobDto.safeParse(invalid).success).toBe(false);
  const failed: unknown = {
    ...invalid,
    result: {
      ...invalid.result,
      numericalStatus: 'FAILED',
      signedReductionM3: null,
      signedPeakReductionM3s: null,
      cases: [
        invalid.result.cases[0],
        {
          ...invalid.result.cases[1],
          numericalStatus: 'FAILED',
          pumpOperation: {
            ...invalid.result.cases[1].pumpOperation,
            curveStatus: 'FAILED',
            pumps: [
              {
                ...invalid.result.cases[1].pumpOperation.pumps[0],
                curveStatus: 'FAILED',
                shaftEnergyKwh: null,
              },
            ],
          },
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<WatershedResult job={watershedJobDto.parse(failed)} />);
  expect(html).toContain('범위 이탈로 산정 보류');
  expect(html).toContain('내부 이송');
  expect(html).not.toContain('125.47 m³ 감소');
});
