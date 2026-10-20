import { scenePointer, clearScenePointer } from '../../city/service/mapCursor';
import { memo, useEffect, useMemo } from 'react';
import { DoubleSide, ShapeGeometry, ExtrudeGeometry } from 'three';
import type { InfrastructureAsset } from '../entity/infrastructure';
import type { Terrain } from '../../terrain/entity/terrain';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import { terrainHeight } from '../../terrain/service/terrainService';
import { infrastructureColor } from '../service/infrastructureService';

type Props = {
  assets: InfrastructureAsset[];
  selectedId: string;
  onSelect?: (asset: InfrastructureAsset) => void;
};
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
      onPointerMove={(event) => scenePointer(event, 'inspect')}
      onPointerOut={clearScenePointer}
      onClick={(event) => {
        if (event.delta > 5) return;
        event.stopPropagation();
        onSelect?.(asset);
      }}
    >
      <meshStandardMaterial
        color={selected ? '#dda62e' : infrastructureColor(asset)}
        roughness={0.48}
        metalness={0.12}
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
