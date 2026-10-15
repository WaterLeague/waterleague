import type { Building } from '../entity/catalog';
export function heightDescription(building: Building): string {
  return ({ OSM_TAG: 'OSM 높이 표기', LEVELS_ESTIMATE: '층수 기반 추정', VISUAL_ASSUMPTION: '시각화용 가정' })[building.heightSource];
}
export function buildingLabel(building: Building): string { return building.name || `건물 ${building.id.split('/')[1]}`; }
