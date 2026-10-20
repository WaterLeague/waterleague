import { Line } from '@react-three/drei';
import { terrainHeight } from '../../terrain/service/terrainService';
import type { Terrain } from '../../terrain/entity/terrain';
import { cisternDisplay } from '../service/cisternDisplayService';
import type { MapPoint } from '../entity/facilityFootprint';

export function CisternInstallationMesh({
  cell,
  areaM2,
  terrain,
  opacity,
  preview,
}: {
  cell: { heightM: number; polygons?: MapPoint[][][]; coordinates?: MapPoint[] };
  areaM2: number;
  terrain: Terrain | null;
  opacity: number;
  preview: boolean;
}) {
  const layout = cisternDisplay(cell, areaM2);
  const [x, north] = layout.center;
  const ground = terrainHeight(terrain, layout.center) + 0.12 - (cell.heightM + 0.2);
  const alpha = opacity * (preview ? 0.55 : 1);
  return (
    <group>
      <mesh position={[x, ground + 0.5, -north]} castShadow={!preview} receiveShadow>
        <boxGeometry args={[layout.widthM, 1, layout.widthM]} />
        <meshStandardMaterial
          color="#548eae"
          metalness={0.2}
          roughness={0.55}
          transparent={alpha < 1}
          opacity={alpha}
          depthWrite={alpha === 1}
        />
      </mesh>
      <mesh position={[x, ground + 1.04, -north]} castShadow={!preview}>
        <boxGeometry args={[layout.widthM + 0.08, 0.08, layout.widthM + 0.08]} />
        <meshStandardMaterial color="#305e76" transparent={alpha < 1} opacity={alpha} />
      </mesh>
      <Line
        points={[
          [layout.roof[0], 0.4, -layout.roof[1]],
          [layout.roof[0] + 0.25, 0.4, -north],
          [layout.roof[0] + 0.25, ground + 0.8, -north],
          [x, ground + 0.8, -north],
        ]}
        color="#315d73"
        lineWidth={3}
        transparent
        opacity={alpha}
      />
    </group>
  );
}
