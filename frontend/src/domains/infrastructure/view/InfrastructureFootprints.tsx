import { memo, useEffect, useMemo } from 'react';
import { DoubleSide, ShapeGeometry } from 'three';
import type { InfrastructureAsset } from '../entity/infrastructure';
import type { Terrain } from '../../terrain/entity/terrain';
import { polygonPath, polygonShapes } from '../../catalog/service/mapGeometryService';
import { terrainHeight } from '../../terrain/service/terrainService';
import { infrastructureColor } from '../service/infrastructureService';

type Props = { assets: InfrastructureAsset[]; selectedId: string };
export const InfrastructureFootprintsPlan = memo(function InfrastructureFootprintsPlan({
  assets,
  selectedId,
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
    <g pointerEvents="none" aria-label="공개 지도 저류 경계">
      {paths.map(({ asset, path }) => (
        <path
          key={asset.id}
          d={path}
          fillRule="evenodd"
          fill={asset.id === selectedId ? '#dda62e' : infrastructureColor(asset)}
          fillOpacity={0.25}
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
}: {
  asset: InfrastructureAsset;
  selected: boolean;
  terrain: Terrain | null;
}) {
  const geometry = useMemo(() => {
    const value = new ShapeGeometry(polygonShapes(asset.footprint!.polygons));
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
  }, [asset.footprint, terrain]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} raycast={() => {}} renderOrder={5}>
      <meshBasicMaterial
        color={selected ? '#dda62e' : infrastructureColor(asset)}
        side={DoubleSide}
        transparent
        opacity={selected ? 0.45 : 0.25}
        depthWrite={false}
      />
    </mesh>
  );
});

export const InfrastructureFootprints = memo(function InfrastructureFootprints({
  assets,
  selectedId,
  terrain,
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
          />
        ))}
    </>
  );
});
