import { memo, useLayoutEffect, useRef } from 'react';
import { Color, InstancedMesh, Object3D } from 'three';
import { useThree } from '@react-three/fiber';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import { useCityOverview, overviewInstanceLimit as LIMIT } from '../controller/useCityOverview';
export const CityOverview = memo(function CityOverview({
  center,
  distance,
  terrain,
  detailTileIds,
  ownDistrictId,
}: {
  center: [number, number];
  distance: number;
  terrain: Terrain | null;
  detailTileIds: ReadonlySet<string>;
  ownDistrictId: string | null;
}) {
  const mesh = useRef<InstancedMesh>(null),
    invalidate = useThree((state) => state.invalidate);
  const { data, visible, failed } = useCityOverview(center, distance, detailTileIds);
  useLayoutEffect(() => {
    if (!mesh.current || !data) return;
    const object = new Object3D(),
      color = new Color();
    for (const [index, building] of visible.entries()) {
      const [east, north, width, depth, height, district] = building;
      const ground = Math.max(
        ...[-1, 1].flatMap((x) =>
          [-1, 1].map((y) =>
            terrainMeshHeight(terrain, [east + (x * width) / 2, north + (y * depth) / 2])
          )
        )
      );
      object.position.set(east, ground + height / 2 + 0.03, -north);
      object.scale.set(width, height, depth);
      object.updateMatrix();
      mesh.current.setMatrixAt(index, object.matrix);
      color.set(
        ownDistrictId && data.districts[district] !== ownDistrictId ? '#c4ccbf' : '#d5d7ca'
      );
      mesh.current.setColorAt(index, color);
    }
    mesh.current.count = visible.length;
    mesh.current.instanceMatrix.needsUpdate = true;
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
    mesh.current.computeBoundingSphere();
    invalidate();
  }, [visible, data, terrain, ownDistrictId, invalidate]);
  if (failed) throw new Error('축소 지도 표시 실패');
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, LIMIT]} count={0} raycast={() => {}}>
      <boxGeometry />
      <meshStandardMaterial color="#ffffff" roughness={0.95} />
    </instancedMesh>
  );
});
