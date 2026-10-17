import type { InfrastructureAsset } from '../entity/infrastructure';
export const infrastructureNames: Record<InfrastructureAsset['kind'], string> = {
  STORM_PUMP: '빗물펌프장',
  RAINWATER_FACILITY: '빗물관리시설',
  INFILTRATION_OTHER: '기타 침투시설',
  INFILTRATION_GUTTER: '침투측구',
  INFILTRATION_PIT: '침투통',
  INFILTRATION_TRENCH: '침투 트렌치',
  RAINWATER_REUSE: '빗물이용시설',
};
export function visibleInfrastructure(
  assets: InfrastructureAsset[],
  center: readonly number[],
  distance: number,
  selectedId: string
) {
  return assets.filter(
    (a) =>
      a.id === selectedId ||
      ((distance < 9000 || a.kind === 'STORM_PUMP') &&
        Math.hypot(a.center[0] - center[0], a.center[1] - center[1]) < distance * 1.5)
  );
}
export const infrastructureColor = (asset: InfrastructureAsset) =>
  asset.kind === 'STORM_PUMP' ? '#244a78' : '#217d88';
