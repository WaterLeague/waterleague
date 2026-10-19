import { useMemo } from 'react';
import type { InfrastructureAsset } from '../entity/infrastructure';
import { visibleInfrastructure } from '../service/infrastructureService';

export function useVisibleInfrastructure(
  assets: InfrastructureAsset[] | undefined,
  enabled: boolean,
  center: [number, number],
  distance: number,
  selectedId: string
) {
  const key = JSON.stringify(
    enabled && assets
      ? visibleInfrastructure(assets, center, distance, selectedId)
          .map((a) => a.id)
          .sort()
      : []
  );
  // 시야에 포함된 시설이 같으면 카메라 이동으로 건물 분류를 다시 만들지 않는다.
  return useMemo(() => {
    const ids = new Set<string>(JSON.parse(key));
    return assets?.filter((asset) => ids.has(asset.id)) ?? [];
  }, [assets, key]);
}
