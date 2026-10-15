import { expect, it } from 'vitest';
import model from '../../../../../data/models/seongsu-lab.json';
import { mapLab } from '../../game/mapper/labMapper';
import type { Placement } from '../../game/entity/game';
import { availableLimits, exceedsLeagueLimits, totalArea } from './leagueService';

const placement = (cellId: string, areaM2: number): Placement => ({
  cellId,
  areaM2,
  facilityType: 'RAIN_GARDEN',
});

it('소수 면적의 정확한 한도를 허용하고 0.01 m² 초과와 개수 초과 차단', () => {
  const placements = [placement('G1', 10.01), placement('G2', 30.02)];
  const limits = { placementLimit: 2, areaLimitM2: 40.03 };
  expect(totalArea(placements)).toBe(40.03);
  expect(exceedsLeagueLimits(placements, limits)).toBe(false);
  expect(exceedsLeagueLimits([placement('G1', 40.04)], limits)).toBe(true);
  expect(exceedsLeagueLimits(placements, { ...limits, placementLimit: 1 })).toBe(true);
  expect(exceedsLeagueLimits(placements, {})).toBe(false);
});

it('허용 시설에 해당하는 셀만 면적에 포함하고 모델 개수 한도 적용', () => {
  const lab = mapLab({ modelHash: 'a'.repeat(64), model: structuredClone(model) });
  lab.model.maxPlacements = 1;
  lab.model.cells = [
    { ...lab.model.cells[0], id: 'G1', maxAreaM2: 10.01, allowedTypes: ['RAIN_GARDEN'] },
    { ...lab.model.cells[0], id: 'G2', maxAreaM2: 30.02, allowedTypes: ['RAIN_GARDEN'] },
    { ...lab.model.cells[0], id: 'R1', maxAreaM2: 50, allowedTypes: ['GREEN_ROOF'] },
  ];
  expect(availableLimits(lab, ['RAIN_GARDEN'])).toEqual({
    placementLimit: 1,
    areaLimitM2: 40.03,
  });
  expect(availableLimits(lab, [])).toEqual({ placementLimit: 0, areaLimitM2: 0 });
});
