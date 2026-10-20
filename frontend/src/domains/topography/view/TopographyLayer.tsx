import { memo, useEffect, useLayoutEffect, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import { useUrbanLighting } from '../../urban/view/UrbanEnvironment';
import { BufferAttribute, BufferGeometry, DoubleSide, InstancedMesh } from 'three';
import type { TopographyBuffers, TopographyView } from '../entity/topography';
import { pointModelGeometry } from '../service/pointModelGeometry';
import type { PointModelKind } from '../service/pointModelService';
const Tile = memo(function Tile({ data }: { data: TopographyBuffers }) {
  const geometries = useMemo(() => {
    const areas = new BufferGeometry(),
      lines = new BufferGeometry();
    areas.setAttribute('position', new BufferAttribute(data.positions, 3));
    areas.setAttribute('normal', new BufferAttribute(data.normals, 3));
    areas.setAttribute('color', new BufferAttribute(data.colors, 3));
    lines.setAttribute('position', new BufferAttribute(data.lines, 3));
    lines.setAttribute('color', new BufferAttribute(data.lineColors, 3));
    return { areas, lines };
  }, [data]);
  useEffect(
    () => () => {
      for (const geometry of Object.values(geometries)) geometry.dispose();
    },
    [geometries]
  );
  return (
    <group>
      {data.positions.length > 0 && (
        <mesh geometry={geometries.areas} raycast={() => {}} receiveShadow>
          <meshStandardMaterial vertexColors roughness={0.96} side={DoubleSide} />
        </mesh>
      )}
      {data.lines.length > 0 && (
        <lineSegments geometry={geometries.lines} raycast={() => {}}>
          <lineBasicMaterial vertexColors transparent opacity={0.72} depthWrite={false} />
        </lineSegments>
      )}
    </group>
  );
});
const Models = memo(function Models({
  kind,
  matrices,
  coarse,
}: {
  kind: PointModelKind;
  matrices: Float32Array;
  coarse: boolean;
}) {
  const mesh = useMemo(() => {
    const model = pointModelGeometry(kind, coarse);
    return new InstancedMesh(model.geometry, model.material, matrices.length / 16);
  }, [kind, coarse, matrices.length]);
  useLayoutEffect(() => {
    mesh.instanceMatrix.array.set(matrices);
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [mesh, matrices]);
  useEffect(
    () => () => {
      mesh.dispose();
    },
    [mesh]
  );
  return <primitive object={mesh} dispose={null} raycast={() => {}} receiveShadow />;
});
export const TopographyLayer = memo(function TopographyLayer({
  value,
  distance,
}: {
  value: TopographyView;
  distance: number;
}) {
  const light = useUrbanLighting();
  const lampMaterials = useMemo(
    () => [false, true].map((coarse) => pointModelGeometry('LAMP', coarse).material),
    []
  );
  useFrame(() => {
    for (const material of lampMaterials) material.userData.night.value = light?.night.value ?? 0;
  }, -0.2);
  const cellSize = distance > 1800 ? 5 : distance > 500 ? 2 : 1;
  // 가까이서는 작은 공간 묶음으로 잘라 화면 밖 인스턴스의 GPU 처리를 생략한다.
  const models = useMemo(() => {
    const groups = new Map<string, { kind: PointModelKind; parts: Float32Array[] }>();
    for (const tile of value.tiles)
      for (const model of tile.data.models) {
        const id =
          model.kind +
          ':' +
          Math.floor(model.cell[0] / cellSize) +
          ',' +
          Math.floor(model.cell[1] / cellSize);
        if (!groups.has(id)) groups.set(id, { kind: model.kind, parts: [] });
        groups.get(id)!.parts.push(model.matrices);
      }
    return [...groups].map(([id, { kind, parts }]) => {
      if (parts.length === 1) return { id, kind, matrices: parts[0] };
      const matrices = new Float32Array(parts.reduce((sum, p) => sum + p.length, 0));
      let offset = 0;
      for (const part of parts) {
        matrices.set(part, offset);
        offset += part.length;
      }
      return { id, kind, matrices };
    });
  }, [value.tiles, cellSize]);
  return (
    <group>
      {value.tiles.map((tile) => (
        <Tile key={tile.id} data={tile.data} />
      ))}
      {models.map((model) => (
        <Models key={model.id} {...model} coarse={distance > 1800} />
      ))}
    </group>
  );
});
