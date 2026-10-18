import { memo, useMemo, useEffect } from 'react';
import { BoxGeometry, EdgesGeometry } from 'three';
import type { CisternGeometryPreview } from '../dto/cisternLayoutDto';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
const noRaycast = () => {};
export const CisternLayoutMesh = memo(function CisternLayoutMesh({
  geometry: g,
  terrain,
}: {
  geometry: CisternGeometryPreview;
  terrain: Terrain | null;
}) {
  const lines = useMemo(() => {
    const box = new BoxGeometry(g.outerWidthM, g.storageDepthM, g.outerLengthM);
    const edges = new EdgesGeometry(box);
    box.dispose();
    return edges;
  }, [g.outerWidthM, g.outerLengthM, g.storageDepthM]);
  useEffect(() => () => lines.dispose(), [lines]);
  return (
    <group
      position={[
        g.center[0],
        terrainHeight(terrain, g.center) + g.storageDepthM / 2 + 0.35,
        -g.center[1],
      ]}
      rotation={[0, (g.rotationDeg * Math.PI) / 180, 0]}
    >
      <lineSegments geometry={lines} raycast={noRaycast}>
        <lineBasicMaterial color={g.contained ? '#80542a' : '#b53b29'} />
      </lineSegments>
      <mesh raycast={noRaycast}>
        <boxGeometry args={[g.internalWidthM, g.storageDepthM, g.internalLengthM]} />
        <meshStandardMaterial
          color={g.contained ? '#d4a653' : '#d86a55'}
          transparent
          opacity={0.28}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
});
