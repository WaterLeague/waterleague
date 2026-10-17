import { expect, it } from 'vitest';
import model from '../../../../../data/models/seongsu-lab.json';
import type { Placement, FacilityType } from '../entity/game';
import { mapLab } from '../mapper/labMapper';
import { assessPlacementDraft } from './placementDraftService';

const lab = mapLab({ modelHash: 'a'.repeat(64), model });
const limits = {
  budget: lab.model.budget,
  placementLimit: lab.model.maxPlacements,
  allowedTypes: ['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF'] as FacilityType[],
};
const garden = lab.model.cells.find((c) => c.allowedTypes.includes('RAIN_GARDEN'))!;
const roof = lab.model.cells.find((c) => c.allowedTypes.includes('GREEN_ROOF'))!;

it('미선택·금지 시설·기관 허용 종류를 구분하고 배치 후보 생성 차단', () => {
  expect(assessPlacementDraft(lab, [], null, 'RAIN_GARDEN', 40, limits).issue).toBe('SELECT_CELL');
  expect(assessPlacementDraft(lab, [], roof.id, 'RAIN_GARDEN', 40, limits).issue).toBe(
    'FACILITY_NOT_ALLOWED'
  );
  expect(
    assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', 40, {
      ...limits,
      allowedTypes: ['GREEN_ROOF'],
    }).placement
  ).toBeNull();
});

it('유효한 소수 경계와 실제 배치 면적을 통일하고 비유한·음수·영 면적 차단', () => {
  for (const invalid of [NaN, Infinity, -1, 0, 0.004]) {
    const result = assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', invalid, limits);
    expect(result.issue).toBe('INVALID_AREA');
    expect(result.placement).toBeNull();
    expect(result.projectedCost).toBeNull();
  }
  expect(
    assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', 0.01, limits).placement?.areaM2
  ).toBe(0.01);
  const result = assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', 40.126, limits);
  expect(result.areaM2).toBe(40.13);
  expect(result.placement?.areaM2).toBe(40.13);
});

it('실제 구역 최대 면적의 반올림 경계 검사', () => {
  const generous = { ...limits, budget: 1e12 };
  expect(
    assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', garden.maxAreaM2 + 0.004, generous)
      .issue
  ).toBeNull();
  const result = assessPlacementDraft(
    lab,
    [],
    garden.id,
    'RAIN_GARDEN',
    garden.maxAreaM2 + 0.006,
    generous
  );
  expect(result.issue).toBe('CELL_AREA_LIMIT');
  expect(result.placement).toBeNull();
});

it('교체 시 이전 비용·면적·개수를 제외하고 원본 배치 보존', () => {
  const placements: Placement[] = [{ cellId: garden.id, facilityType: 'RAIN_GARDEN', areaM2: 40 }];
  const before = structuredClone(placements);
  const result = assessPlacementDraft(lab, placements, garden.id, 'RAIN_GARDEN', 20, {
    ...limits,
    budget: 20 * lab.model.unitCosts.RAIN_GARDEN,
    placementLimit: 1,
    areaLimitM2: 20,
  });
  expect(result.issue).toBeNull();
  expect(result.projectedCost).toBe(20 * lab.model.unitCosts.RAIN_GARDEN);
  expect(placements).toEqual(before);
});

it('추가 배치의 개수·합계 면적 초과를 개별 사유로 표시', () => {
  const placements: Placement[] = [{ cellId: roof.id, facilityType: 'GREEN_ROOF', areaM2: 20 }];
  expect(
    assessPlacementDraft(lab, placements, garden.id, 'RAIN_GARDEN', 10, {
      ...limits,
      placementLimit: 1,
    }).issue
  ).toBe('PLACEMENT_LIMIT');
  expect(
    assessPlacementDraft(lab, placements, garden.id, 'RAIN_GARDEN', 10, {
      ...limits,
      areaLimitM2: 30,
    }).issue
  ).toBeNull();
  const result = assessPlacementDraft(lab, placements, garden.id, 'RAIN_GARDEN', 10.01, {
    ...limits,
    areaLimitM2: 30,
  });
  expect(result.issue).toBe('TOTAL_AREA_LIMIT');
  expect(result.message).toContain('0.01 m²');
});

it('예산 상한과 초과분 안내에 같은 후보 비용 사용', () => {
  const budget = 10 * lab.model.unitCosts.RAIN_GARDEN;
  expect(
    assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', 10, { ...limits, budget }).issue
  ).toBeNull();
  const result = assessPlacementDraft(lab, [], garden.id, 'RAIN_GARDEN', 11, { ...limits, budget });
  expect(result.issue).toBe('BUDGET_LIMIT');
  expect(result.placement).toBeNull();
  expect(result.projectedCost).toBe(11 * lab.model.unitCosts.RAIN_GARDEN);
  expect(result.message).toContain(
    new Intl.NumberFormat('ko-KR').format(lab.model.unitCosts.RAIN_GARDEN) + '원'
  );
});
