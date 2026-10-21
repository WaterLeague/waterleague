import { memo, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, Object3D } from 'three';
import type { Street, UrbanTime } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import { distanceToStreet, streetPath } from '../service/streetLifeService';
import { streetHeight, submergedSourcePath } from '../service/streetGeometryService';
import { activeRailTrains, railServices } from '../service/railLifeService';
import { urbanAnimationTime } from '../service/urbanTimeService';
const LIMIT = 128;
export const RailLife = memo(function RailLife({
  roads,
  terrain,
  center,
  distance,
  clock,
  animate,
}: {
  roads: Street[];
  terrain: Terrain | null;
  center: [number, number];
  distance: number;
  clock: UrbanTime;
  animate: boolean;
}) {
  const body = useRef<InstancedMesh>(null),
    windows = useRef<InstancedMesh>(null),
    roof = useRef<InstancedMesh>(null),
    bogies = useRef<InstancedMesh>(null);
  const model = useMemo(() => new Object3D(), []);
  const blue = useMemo(() => new Color('#3a76a6'), []),
    red = useMemo(() => new Color('#aa4546'), []);
  const last = useRef(0);
  const paths = useMemo(() => roads.filter((r) => r.nativeRailKind).map(streetPath), [roads]);
  const x = Math.round(center[0] / 100) * 100,
    y = Math.round(center[1] / 100) * 100;
  const services = useMemo(() => railServices(paths), [paths]);
  const nearby = useMemo(
    () =>
      paths
        .map((path) => ({ path, d: distanceToStreet(path, x, y) }))
        .filter((p) => p.d < 2800)
        .sort((a, b) => a.d - b.d || a.path.road.id.localeCompare(b.path.road.id))
        .map((p) => p.path.road.id),
    [paths, x, y]
  );
  const visible = useMemo(() => new Set(nearby), [nearby]);
  useFrame(() => {
    last.current = urbanAnimationTime(clock, last.current, animate);
    const seconds = last.current;
    let count = 0;
    const put = (
      mesh: InstancedMesh | null,
      index: number,
      x: number,
      h: number,
      z: number,
      sx: number,
      sy: number,
      sz: number,
      yaw: number,
      pitch: number
    ) => {
      if (!mesh) return;
      model.position.set(x, h, z);
      model.scale.set(sx, sy, sz);
      model.rotation.set(pitch, yaw, 0, 'YXZ');
      model.updateMatrix();
      mesh.setMatrixAt(index, model.matrix);
    };
    if (distance < 8500)
      for (const { path, cars } of activeRailTrains(services, seconds)) {
        if (!visible.has(path.road.id)) continue;
        for (const car of cars) {
          if (count === LIMIT) break;
          if (
            [car.center, car.front, car.back].some((p) =>
              submergedSourcePath(path.road, terrain, [p.x, p.y])
            )
          )
            continue;
          const height = streetHeight(terrain, [car.center.x, car.center.y], path.road);
          const front = streetHeight(terrain, [car.front.x, car.front.y], path.road),
            back = streetHeight(terrain, [car.back.x, car.back.y], path.road);
          const yaw = Math.atan2(car.front.x - car.back.x, -(car.front.y - car.back.y));
          const pitch = -Math.atan2(front - back, 16);
          put(
            body.current,
            count,
            car.center.x,
            height + 1.8,
            -car.center.y,
            2.8,
            2.6,
            18,
            yaw,
            pitch
          );
          put(
            windows.current,
            count,
            car.center.x,
            height + 2.35,
            -car.center.y,
            2.84,
            0.7,
            16.2,
            yaw,
            pitch
          );
          put(
            roof.current,
            count,
            car.center.x,
            height + 3.2,
            -car.center.y,
            2.6,
            0.25,
            17.5,
            yaw,
            pitch
          );
          put(
            bogies.current,
            count,
            car.center.x,
            height + 0.45,
            -car.center.y,
            2.25,
            0.5,
            15.5,
            yaw,
            pitch
          );
          body.current?.setColorAt(count, path.road.nativeRailKind === 'subway' ? blue : red);
          count++;
        }
      }
    for (const ref of [body, windows, roof, bogies])
      if (ref.current) {
        ref.current.count = count;
        ref.current.instanceMatrix.needsUpdate = true;
        if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true;
      }
  });
  return (
    <group name="공개 철도 선형 기반 표시용 운행">
      <instancedMesh ref={body} args={[undefined, undefined, LIMIT]} frustumCulled={false}>
        <boxGeometry />
        <meshStandardMaterial roughness={0.65} />
      </instancedMesh>
      <instancedMesh ref={windows} args={[undefined, undefined, LIMIT]} frustumCulled={false}>
        <boxGeometry />
        <meshStandardMaterial color="#163744" roughness={0.25} />
      </instancedMesh>
      <instancedMesh ref={roof} args={[undefined, undefined, LIMIT]} frustumCulled={false}>
        <boxGeometry />
        <meshStandardMaterial color="#ced5d6" roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={bogies} args={[undefined, undefined, LIMIT]} frustumCulled={false}>
        <boxGeometry />
        <meshStandardMaterial color="#30393b" />
      </instancedMesh>
    </group>
  );
});
