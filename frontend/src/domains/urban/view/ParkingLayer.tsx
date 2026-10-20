import { scenePointer, clearScenePointer } from '../../city/service/mapCursor';
import { memo, useMemo, useEffect, useLayoutEffect, useRef } from 'react';
import { useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { Color, InstancedMesh, Object3D, DoubleSide } from 'three';
import type { ParkingLot } from '../entity/parking';
import type { Terrain } from '../../terrain/entity/terrain';
import type { FloodField } from '../service/floodFieldService';
import { parkingGeometry } from '../service/parkingGeometryService';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import { emptyFloodStats, type FloodStats } from '../service/floodMovementService';
import type { UrbanTime } from '../entity/urban';
import { urbanTime } from '../service/urbanTimeService';
import {
  bridgeDeckHeight,
  bridgeDeckThickness,
  streetAtFace,
} from '../service/streetGeometryService';
const COLORS = ['#d9dadd', '#ede7d6', '#345e79', '#a33e33', '#252d34', '#a4afb2'];
const LIMIT = 400;
export const ParkingLayer = memo(function ParkingLayer({
  lots,
  terrain,
  center,
  flood,
  clock,
  animate,
  onFloodStats,
  onParking,
}: {
  lots: ParkingLot[];
  terrain: Terrain | null;
  center: [number, number];
  flood: FloodField;
  clock: UrbanTime;
  animate: boolean;
  onFloodStats: (stats: FloodStats) => void;
  onParking?: (sourceId: string, point: [number, number]) => void;
}) {
  const geometry = useMemo(() => parkingGeometry(lots, terrain), [lots, terrain]);
  useEffect(
    () => () => {
      geometry.surface.dispose();
      geometry.markings.dispose();
      geometry.hit.dispose();
    },
    [geometry]
  );
  const slots = useMemo(
    () =>
      lots
        .flatMap((lot) => lot.slots.map((slot) => ({ ...slot, lotId: lot.id })))
        .filter((slot) => slot.seed < 0.65)
        .sort(
          (a, b) =>
            Math.hypot(a.center[0] - center[0], a.center[1] - center[1]) -
            Math.hypot(b.center[0] - center[0], b.center[1] - center[1])
        )
        .slice(0, LIMIT),
    [lots, center]
  );
  const cars = useRef<InstancedMesh>(null),
    roofs = useRef<InstancedMesh>(null),
    wheels = useRef<InstancedMesh>(null),
    columns = useRef<InstancedMesh>(null),
    capitals = useRef<InstancedMesh>(null),
    signals = useRef<InstancedMesh>(null);
  const supports = useMemo(() => lots.flatMap((lot) => lot.supports).slice(0, 1000), [lots]);
  const model = useMemo(() => new Object3D(), []),
    color = useMemo(() => new Color(), []);
  const invalidate = useThree((state) => state.invalidate);
  useLayoutEffect(() => {
    const put = (
      mesh: InstancedMesh | null,
      index: number,
      x: number,
      y: number,
      z: number,
      sx: number,
      sy: number,
      sz: number,
      angle: number
    ) => {
      if (!mesh) return;
      model.position.set(x, y, z);
      model.scale.set(sx, sy, sz);
      model.rotation.set(0, angle, 0);
      model.updateMatrix();
      mesh.setMatrixAt(index, model.matrix);
    };
    supports.forEach((support, i) => {
      const [x, y] = support.center,
        base = terrainMeshHeight(terrain, support.center),
        height = bridgeDeckHeight - bridgeDeckThickness;
      put(columns.current, i, x, base + height / 2, -y, 1.2, height, 1.2, 0);
      put(
        capitals.current,
        i,
        x,
        base + height - 0.25,
        -y,
        Math.min(6, support.width * 0.6),
        0.5,
        1.5,
        support.angle + Math.PI / 2
      );
    });
    let exposed = 0;
    slots.forEach((slot, i) => {
      const [x, y] = slot.center,
        h = terrainMeshHeight(terrain, slot.center) + 0.08,
        dx = Math.sin(slot.angle),
        dz = Math.cos(slot.angle);
      put(cars.current, i, x, h + 0.65, -y, 1.75, 0.8, 4.1, slot.angle);
      put(roofs.current, i, x, h + 1.22, -y, 1.5, 0.55, 2.2, slot.angle);
      color.set(COLORS[Math.floor(slot.seed * 100) % COLORS.length]);
      cars.current?.setColorAt(i, color);
      for (let k = 0; k < 4; k++) {
        const side = (k % 2 ? 1 : -1) * 0.86,
          along = (k < 2 ? 1 : -1) * 1.3;
        put(
          wheels.current,
          i * 4 + k,
          x + dx * along + dz * side,
          h + 0.32,
          -y + dz * along - dx * side,
          0.22,
          0.5,
          0.65,
          slot.angle
        );
      }
      const contact = flood.contact(slot.center);
      if (contact)
        put(
          signals.current,
          exposed++,
          x,
          h + Math.max(2.8, contact.depth ?? 0),
          -y,
          0.7,
          0.7,
          0.7,
          0
        );
    });
    for (const [ref, count] of [
      [cars, slots.length],
      [roofs, slots.length],
      [wheels, slots.length * 4],
      [columns, supports.length],
      [capitals, supports.length],
      [signals, exposed],
    ] as const) {
      if (!ref.current) continue;
      ref.current.count = count;
      ref.current.instanceMatrix.needsUpdate = true;
      if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true;
    }
    onFloodStats({ ...emptyFloodStats, exposed });
    invalidate();
  }, [slots, supports, terrain, flood, model, color, invalidate, onFloodStats]);
  useEffect(() => () => onFloodStats(emptyFloodStats), [onFloodStats]);
  useFrame(() => {
    const at = urbanTime(clock);
    if (signals.current)
      signals.current.visible = !animate || at == null || Math.sin(at / 250) > -0.3;
  }, -0.2);
  const selectCar = (event: ThreeEvent<MouseEvent>, wheel = false) => {
    event.stopPropagation();
    if (event.delta > 4 || event.instanceId == null) return;
    const slot = slots[wheel ? Math.floor(event.instanceId / 4) : event.instanceId];
    if (slot) onParking?.(slot.lotId, slot.center);
  };
  return (
    <group>
      <mesh
        geometry={geometry.hit}
        onPointerMove={(event) => scenePointer(event, 'install')}
        onPointerOut={clearScenePointer}
        onClick={(event) => {
          event.stopPropagation();
          if (event.delta > 4) return;
          const index = streetAtFace(geometry.hitEnds, event.faceIndex ?? -1);
          if (index >= 0) onParking?.(lots[index].id, [event.point.x, -event.point.z]);
        }}
      >
        <meshBasicMaterial
          transparent
          opacity={0}
          depthWrite={false}
          colorWrite={false}
          side={DoubleSide}
        />
      </mesh>
      <instancedMesh
        ref={columns}
        args={[undefined, undefined, 1000]}
        frustumCulled={false}
        raycast={() => {}}
      >
        <boxGeometry />
        <meshStandardMaterial color="#929b9b" roughness={0.95} />
      </instancedMesh>
      <instancedMesh
        ref={capitals}
        args={[undefined, undefined, 1000]}
        frustumCulled={false}
        raycast={() => {}}
      >
        <boxGeometry />
        <meshStandardMaterial color="#aab1b0" roughness={0.95} />
      </instancedMesh>
      <mesh geometry={geometry.surface} receiveShadow raycast={() => {}}>
        <meshStandardMaterial color="#858780" roughness={0.95} side={DoubleSide} />
      </mesh>
      <lineSegments geometry={geometry.markings} raycast={() => {}}>
        <lineBasicMaterial color="#e5e0cf" />
      </lineSegments>
      <instancedMesh
        ref={cars}
        args={[undefined, undefined, LIMIT]}
        frustumCulled={false}
        onPointerMove={(event) => scenePointer(event, 'install')}
        onPointerOut={clearScenePointer}
        onClick={(event) => selectCar(event)}
      >
        <boxGeometry />
        <meshStandardMaterial roughness={0.5} />
      </instancedMesh>
      <instancedMesh
        ref={roofs}
        args={[undefined, undefined, LIMIT]}
        frustumCulled={false}
        onPointerMove={(event) => scenePointer(event, 'install')}
        onPointerOut={clearScenePointer}
        onClick={(event) => selectCar(event)}
      >
        <boxGeometry />
        <meshStandardMaterial color="#283b4c" roughness={0.3} />
      </instancedMesh>
      <instancedMesh
        ref={wheels}
        args={[undefined, undefined, LIMIT * 4]}
        frustumCulled={false}
        onPointerMove={(event) => scenePointer(event, 'install')}
        onPointerOut={clearScenePointer}
        onClick={(event) => selectCar(event, true)}
      >
        <boxGeometry />
        <meshStandardMaterial color="#232529" roughness={1} />
      </instancedMesh>
      <instancedMesh
        ref={signals}
        args={[undefined, undefined, LIMIT]}
        frustumCulled={false}
        raycast={() => {}}
      >
        <octahedronGeometry />
        <meshBasicMaterial color="#ef5c44" toneMapped={false} />
      </instancedMesh>
    </group>
  );
});
