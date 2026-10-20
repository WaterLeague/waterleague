import { memo, useMemo, useEffect } from 'react';
import { BoxGeometry, EdgesGeometry } from 'three';
import type { CisternMapPreview } from '../dto/cisternLayoutDto';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
const noRaycast = () => {};
export const CisternLayoutMesh = memo(function CisternLayoutMesh({
  geometry: g,
  terrain,
}: {
  geometry: CisternMapPreview;
  terrain: Terrain | null;
}) {
  const publicEquipment = g.method === 'PUBLIC_EQUIPMENT_ENVELOPE_V1';
  const width = publicEquipment ? g.widthM : g.outerWidthM,
    length = publicEquipment ? g.lengthM : g.outerLengthM,
    height = publicEquipment ? g.heightM : g.storageDepthM;
  const lines = useMemo(() => {
    const box = new BoxGeometry(width, height, length);
    const edges = new EdgesGeometry(box);
    box.dispose();
    return edges;
  }, [width, length, height]);
  useEffect(() => () => lines.dispose(), [lines]);
  return (
    <group
      position={[g.center[0], terrainHeight(terrain, g.center) + height / 2 + 0.35, -g.center[1]]}
      rotation={[0, (g.rotationDeg * Math.PI) / 180, 0]}
    >
      <lineSegments geometry={lines} raycast={noRaycast}>
        <lineBasicMaterial color={g.contained ? '#80542a' : '#b53b29'} />
      </lineSegments>
      <mesh raycast={noRaycast}>
        <boxGeometry
          args={[
            publicEquipment ? width : g.internalWidthM,
            height,
            publicEquipment ? length : g.internalLengthM,
          ]}
        />
        <meshStandardMaterial
          color={g.contained ? (publicEquipment ? '#b7c2c9' : '#d4a653') : '#d86a55'}
          transparent
          opacity={publicEquipment ? 0.75 : 0.28}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
});
