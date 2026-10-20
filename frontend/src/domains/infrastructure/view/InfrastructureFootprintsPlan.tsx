import { memo, useMemo } from 'react';
import type { InfrastructureAsset } from '../entity/infrastructure';
import { polygonPath } from '../../catalog/service/mapGeometryService';
import { infrastructureColor } from '../service/infrastructureService';

type Props = {
  assets: InfrastructureAsset[];
  selectedId: string;
  onSelect?: (asset: InfrastructureAsset) => void;
};
export const InfrastructureFootprintsPlan = memo(function InfrastructureFootprintsPlan({
  assets,
  selectedId,
  onSelect,
}: Props) {
  const paths = useMemo(
    () =>
      assets
        .filter((a) => a.footprint)
        .map((asset) => ({
          asset,
          path: polygonPath(asset.footprint!.polygons),
        })),
    [assets]
  );
  return (
    <g aria-label="공개 지도 시설 경계">
      {paths.map(({ asset, path }) => (
        <path
          key={asset.id}
          d={path}
          fillRule="evenodd"
          fill={asset.id === selectedId ? '#dda62e' : infrastructureColor(asset)}
          fillOpacity={asset.footprint?.buildingId ? 0.9 : 0.25}
          data-map-cursor="inspect"
          onClick={(event) => {
            event.stopPropagation();
            onSelect?.(asset);
          }}
          stroke={asset.id === selectedId ? '#b87a13' : infrastructureColor(asset)}
          strokeWidth={asset.id === selectedId ? 2 : 1}
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  );
});
