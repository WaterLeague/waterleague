import type { InfrastructureAsset } from '../entity/infrastructure';
export const infrastructureNames: Record<InfrastructureAsset['kind'], string> = {
  STORM_PUMP: '빗물펌프장',
  RAINWATER_FACILITY: '빗물관리시설',
  INFILTRATION_OTHER: '기타 침투시설',
  INFILTRATION_GUTTER: '침투측구',
  INFILTRATION_PIT: '침투통',
  INFILTRATION_TRENCH: '침투 트렌치',
  RAINWATER_REUSE: '빗물이용시설',
  RETENTION_BASIN: '저류·유수 영역',
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
      ((distance < 9000 || a.kind === 'STORM_PUMP' || a.footprint) &&
        Math.hypot(a.center[0] - center[0], a.center[1] - center[1]) < distance * 1.5)
  );
}
export const infrastructureColor = (asset: InfrastructureAsset) =>
  asset.kind === 'STORM_PUMP' ? '#244a78' : '#217d88';

export function publicInfrastructureBuildingIds(assets: InfrastructureAsset[]) {
  return new Set(
    assets.flatMap((a) =>
      a.footprint?.buildingId
        ? [a.footprint.buildingId.replace(/^W/, 'way/').replace(/^R/, 'relation/')]
        : []
    )
  );
}

export function unreservedRoofIds(
  roofIds: ReadonlySet<string>,
  assets: InfrastructureAsset[] | null
) {
  if (!assets) return new Set<string>();
  const reserved = publicInfrastructureBuildingIds(assets);
  return new Set([...roofIds].filter((id) => !reserved.has(id)));
}
