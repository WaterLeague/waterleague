import { useEffect, useMemo } from 'react';
import { BufferAttribute, BufferGeometry, DoubleSide, ShapeGeometry } from 'three';
import type { WatershedMapSelection } from '../service/watershedMap';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight, terrainLine } from '../../terrain/service/terrainService';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
export function WatershedMapMesh({
  map,
  selectedId,
  disabled,
  onSelect,
  terrain,
}: WatershedMapSelection & { terrain: Terrain | null }) {
  const meshes = useMemo(
    () =>
      map.catchments.map((c) => {
        const geometry = new ShapeGeometry(polygonShapes([[c.points]]));
        const positions = geometry.getAttribute('position');
        for (let i = 0; i < positions.count; i++) {
          const x = positions.getX(i),
            y = positions.getY(i);
          positions.setXYZ(i, x, terrainHeight(terrain, [x, y]) + 0.6, -y);
        }
        geometry.computeVertexNormals();
        return { id: c.id, geometry };
      }),
    [map, terrain]
  );
  const lines = useMemo(() => {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      'position',
      new BufferAttribute(
        new Float32Array(map.links.flatMap((l) => terrainLine(terrain, l.points, 1))),
        3
      )
    );
    return geometry;
  }, [map, terrain]);
  useEffect(
    () => () => {
      meshes.forEach((m) => m.geometry.dispose());
      lines.dispose();
    },
    [meshes, lines]
  );
  return (
    <group>
      {meshes.map(({ id, geometry }) => (
        <mesh
          key={id}
          geometry={geometry}
          renderOrder={9}
          userData={{ watershedSelection: !disabled }}
          onClick={(event) => {
            event.stopPropagation();
            if (!disabled) onSelect(id);
          }}
        >
          <meshBasicMaterial
            color={id === selectedId ? '#f2b43b' : '#2c879a'}
            side={DoubleSide}
            transparent
            opacity={id === selectedId ? 0.28 : 0.1}
            depthWrite={false}
            depthTest={false}
          />
        </mesh>
      ))}
      <lineSegments geometry={lines} renderOrder={10} raycast={() => {}}>
        <lineBasicMaterial color="#16435f" depthTest={false} />
      </lineSegments>
    </group>
  );
}
