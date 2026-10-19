import type { InfrastructureAsset, InfrastructureMarker } from '../entity/infrastructure';
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
      Math.hypot(a.center[0] - center[0], a.center[1] - center[1]) < distance * 1.5
  );
}
export const infrastructureColor = (asset: InfrastructureAsset) =>
  asset.kind === 'STORM_PUMP' ? '#7061d8' : '#9762d9';

export function infrastructureMarkers(
  assets: InfrastructureAsset[],
  distance: number,
  selectedId: string
): InfrastructureMarker[] {
  if (distance < 1600) return assets;
  const spacing = distance * 0.12;
  const buckets = new Map<string, InfrastructureAsset[]>();
  for (const asset of assets) {
    const key =
      asset.id === selectedId
        ? asset.id
        : `${Math.floor(asset.center[0] / spacing)}:${Math.floor(asset.center[1] / spacing)}`;
    const bucket = buckets.get(key) ?? [];
    bucket.push(asset);
    buckets.set(key, bucket);
  }
  // 묶음 표식만 대표 좌표를 사용하며 원본 경계와 개별 시설 좌표는 보존한다.
  return [...buckets.values()].map((values) => ({ ...values[0], clusterCount: values.length }));
}

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
