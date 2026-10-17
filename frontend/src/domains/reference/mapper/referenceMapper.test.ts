import { describe, expect, it } from 'vitest';
import newReport from '../../../../../data/derived/cpu-reference-ngii-v2.json';
import newModel from '../../../../../data/models/seongsu-ngii-v2-421-20240718.json';
import report from '../../../../../data/derived/cpu-reference.json';
import model from '../../../../../data/models/seongsu-lab.json';
import { mapReference } from './referenceMapper';
import { canCopyReference } from '../service/referenceService';
import { mapLab } from '../../game/mapper/labMapper';
const fixture = () => ({ reportHash: 'a'.repeat(64), report: structuredClone(report) });
describe('CPU 기준안 계약', () => {
  it('수치지형도 기준안은 해당 모델에서만 조회·복사 허용', () => {
    const hash = newReport.trainingModelHash;
    const data = mapReference({ reportHash: 'b'.repeat(64), report: newReport }, hash);
    const lab = mapLab({ modelHash: hash, model: newModel });
    expect(canCopyReference(lab, data.report.plans[0])).toBe(true);
    expect(data.report.plans[0].placements.every((p) => p.areaM2 <= 20)).toBe(true);
    expect(() => mapReference(fixture(), hash)).toThrow();
    expect(() =>
      mapReference({ reportHash: 'b'.repeat(64), report: newReport }, report.trainingModelHash)
    ).toThrow();
    expect(canCopyReference(lab, mapReference(fixture()).report.plans[0])).toBe(false);
  });
  it('실제 자료와 현재 모델 비용·면적 일치 시 복사 허용', () => {
    const data = mapReference(fixture());
    const lab = mapLab({ modelHash: report.modelHashes[0], model });
    expect(canCopyReference(lab, data.report.plans[0])).toBe(true);
    expect(canCopyReference({ ...lab, modelHash: 'b'.repeat(64) }, data.report.plans[0])).toBe(
      false
    );
    expect(
      canCopyReference(
        {
          ...lab,
          model: { ...lab.model, unitCosts: { ...lab.model.unitCosts, PERMEABLE_PAVEMENT: 1 } },
        },
        data.report.plans[0]
      )
    ).toBe(false);
  });
  it('예산 초과·비교 강우 중복·탐색 강우 표시 변조 거부', () => {
    const a = fixture();
    a.report.plans[0].cost = a.report.plans[0].budget + 1;
    expect(() => mapReference(a)).toThrow();
    const b = fixture();
    b.report.plans[0].evaluations[0] = b.report.plans[0].evaluations[1];
    expect(() => mapReference(b)).toThrow();
    const c = fixture();
    c.report.plans[0].evaluations[0].role = 'SEARCH_INPUT';
    expect(() => mapReference(c)).toThrow();
  });
  it('공식 검증 주장·표본 범위·탐색 횟수 불일치 거부', () => {
    const a = fixture();
    a.report.official = true;
    expect(() => mapReference(a)).toThrow();
    const b = fixture();
    b.report.plans[0].sampleScoreRange.min += 1;
    expect(() => mapReference(b)).toThrow();
    const c = fixture();
    c.report.uniqueCandidateEvaluations = c.report.totalCandidateRequests + 1;
    expect(() => mapReference(c)).toThrow();
  });
  it('별도 강우에서 성능이 나빠진 음수 점수 보존', () => {
    const data = fixture(),
      plan = data.report.plans[0],
      e = plan.evaluations[0];
    e.score = -5;
    e.strategy.accountedDischargeM3 = e.baseline.accountedDischargeM3 * 1.05;
    plan.sampleScoreRange.min = -5;
    expect(mapReference(data).report.plans[0].evaluations[0].score).toBe(-5);
    e.strategy.accountedDischargeM3 = e.baseline.accountedDischargeM3;
    expect(() => mapReference(data)).toThrow();
  });
});
