import { memo, useEffect, useMemo } from 'react';
import { DoubleSide, ShapeGeometry, ExtrudeGeometry } from 'three';
import type { InfrastructureAsset } from '../entity/infrastructure';
import type { Terrain } from '../../terrain/entity/terrain';
import { polygonPath, polygonShapes } from '../../catalog/service/mapGeometryService';
import { terrainHeight } from '../../terrain/service/terrainService';
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

const FootprintMesh = memo(function FootprintMesh({
  asset,
  selected,
  terrain,
  onSelect,
}: {
  asset: InfrastructureAsset;
  selected: boolean;
  terrain: Terrain | null;
  onSelect?: (asset: InfrastructureAsset) => void;
}) {
  const geometry = useMemo(() => {
    const footprint = asset.footprint!;
    if (footprint.buildingId) {
      const value = new ExtrudeGeometry(polygonShapes(footprint.polygons), {
        depth: footprint.displayHeightM!,
        bevelEnabled: false,
      });
      value.rotateX(-Math.PI / 2).translate(0, terrainHeight(terrain, asset.center), 0);
      value.computeBoundingSphere();
      return value;
    }
    const value = new ShapeGeometry(polygonShapes(footprint.polygons));
    const position = value.getAttribute('position');
    // 공개 지도의 수평 경계를 표시 지형에 얹으며 저류 깊이나 용량을 생성하지 않는다.
    for (let i = 0; i < position.count; i++) {
      const x = position.getX(i),
        y = position.getY(i);
      position.setXYZ(i, x, terrainHeight(terrain, [x, y]) + 0.7, -y);
    }
    value.computeVertexNormals();
    value.computeBoundingSphere();
    return value;
  }, [asset.footprint, asset.center, terrain]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh
      geometry={geometry}
      renderOrder={5}
      userData={{ publicAssetMarker: true }}
      onClick={(event) => {
        if (event.delta > 5) return;
        event.stopPropagation();
        onSelect?.(asset);
      }}
    >
      <meshBasicMaterial
        color={selected ? '#dda62e' : infrastructureColor(asset)}
        side={DoubleSide}
        transparent
        opacity={asset.footprint?.buildingId ? 1 : selected ? 0.45 : 0.25}
        depthWrite={!!asset.footprint?.buildingId}
      />
    </mesh>
  );
});

export const InfrastructureFootprints = memo(function InfrastructureFootprints({
  assets,
  selectedId,
  terrain,
  onSelect,
}: Props & { terrain: Terrain | null }) {
  return (
    <>
      {assets
        .filter((a) => a.footprint)
        .map((asset) => (
          <FootprintMesh
            key={asset.id}
            asset={asset}
            selected={asset.id === selectedId}
            terrain={terrain}
            onSelect={onSelect}
          />
        ))}
    </>
  );
});
