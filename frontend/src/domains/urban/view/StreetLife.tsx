import { memo, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, MeshStandardMaterial, Object3D } from 'three';
import type { Street, UrbanTime, Population } from '../entity/urban';
import type { City } from '../../city/entity/city';
import type { Terrain } from '../../terrain/entity/terrain';
import { streetHeight } from '../service/streetGeometryService';
import {
  distanceToStreet,
  movingPosition,
  pathPosition,
  stableSeed,
  streetPath,
} from '../service/streetLifeService';
import { displayDensity, populationAt } from '../service/populationService';
import { urbanTime } from '../service/urbanTimeService';
import { useUrbanLighting } from './UrbanEnvironment';
const LIMIT = 500;
const PALETTE = ['#c9d3d8', '#f3e6c0', '#345e79', '#a33e33', '#252d34', '#d3caba'];
export const StreetLife = memo(function StreetLife({
  roads,
  terrain,
  center,
  distance,
  clock,
  population,
  city,
  animate,
}: {
  roads: Street[];
  terrain: Terrain | null;
  center: [number, number];
  distance: number;
  clock: UrbanTime;
  population: Population | null;
  city: City;
  animate: boolean;
}) {
  const cars = useRef<InstancedMesh>(null),
    roofs = useRef<InstancedMesh>(null),
    fronts = useRef<InstancedMesh>(null),
    backs = useRef<InstancedMesh>(null),
    people = useRef<InstancedMesh>(null),
    heads = useRef<InstancedMesh>(null),
    legs = useRef<InstancedMesh>(null);
  const poles = useRef<InstancedMesh>(null),
    lamps = useRef<InstancedMesh>(null),
    pools = useRef<InstancedMesh>(null);
  const glow = useRef<MeshStandardMaterial>(null),
    light = useUrbanLighting();
  const model = useMemo(() => new Object3D(), []),
    color = useMemo(() => new Color(), []),
    lastTime = useRef<number | null>(null);
  const areas = useMemo(() => new Map(city.districts.map((d) => [d.id, d.areaKm2])), [city]);
  const densityCache = useRef({
    hour: NaN,
    historical: false,
    source: null as Population | null,
    areas,
    values: new Map<string, number>(),
  });
  const x = Math.round(center[0] / 100) * 100,
    y = Math.round(center[1] / 100) * 100;
  const radius = Math.max(450, Math.min(2800, Math.ceil(distance / 250) * 300));
  const paths = useMemo(
    () =>
      roads
        .map(streetPath)
        .map((path) => ({ path, distance: distanceToStreet(path, x, y) }))
        .filter((p) => p.path.length > 25 && p.distance < radius)
        .sort(
          (a, b) =>
            a.distance - b.distance || stableSeed(a.path.road.id) - stableSeed(b.path.road.id)
        )
        .map((p) => p.path),
    [roads, x, y, radius]
  );
  const agents = useMemo(
    () =>
      paths
        .flatMap((path) => {
          const walking =
            (path.road.walk && path.road.class !== 'cycleway') ||
            (path.road.motor &&
              path.road.sidewalk !== 'no' &&
              !/motorway|trunk/.test(path.road.class));
          return [false, true]
            .filter((walk) => (walk ? walking : path.road.motor))
            .flatMap((walking) =>
              Array.from(
                {
                  length: Math.min(24, Math.max(1, Math.floor(path.length / (walking ? 30 : 45)))),
                },
                (_, i) => ({
                  path,
                  walking,
                  seed: stableSeed(path.road.id + ':' + walking + ':' + i),
                  budget: stableSeed(path.road.id + ':budget:' + walking + ':' + i),
                })
              )
            );
        })
        .slice(0, 1600),
    [paths]
  );
  const streetlights = useMemo(
    () =>
      paths
        .filter((p) => p.road.motor && p.road.class !== 'service')
        .flatMap((path) =>
          Array.from({ length: Math.min(60, Math.floor(path.length / 45)) }, (_, i) => ({
            path,
            at: (i + 0.5) * 45,
          }))
        )
        .filter(({ path, at }) => {
          const p = pathPosition(path, at, 0, 1);
          return Math.hypot(p.x - x, p.y - y) < 1800;
        })
        .slice(0, LIMIT),
    [paths, x, y]
  );
  useFrame(() => {
    if (!cars.current || !people.current || !poles.current) return;
    const at = urbanTime(clock);
    if (at == null) return;
    if (animate || lastTime.current == null || !clock.current.playing) lastTime.current = at / 1000;
    const time = lastTime.current;
    let carCount = 0,
      personCount = 0;
    const put = (
      mesh: InstancedMesh | null,
      index: number,
      px: number,
      py: number,
      pz: number,
      sx: number,
      sy: number,
      sz: number,
      angle = 0
    ) => {
      if (!mesh) return;
      model.position.set(px, py, pz);
      model.scale.set(sx, sy, sz);
      model.rotation.set(0, angle, 0);
      model.updateMatrix();
      mesh.setMatrixAt(index, model.matrix);
    };
    const cached = densityCache.current,
      hour = Math.floor(at / 3600000);
    if (
      cached.hour !== hour ||
      cached.historical !== clock.current.historical ||
      cached.source !== population ||
      cached.areas !== areas
    ) {
      cached.hour = hour;
      cached.historical = clock.current.historical;
      cached.source = population;
      cached.areas = areas;
      cached.values = new Map(
        [...areas].map(([district, area]) => [
          district,
          displayDensity(
            populationAt(population, at, district, clock.current.historical)?.people,
            area
          ),
        ])
      );
    }
    if (distance < 8500)
      for (const agent of agents) {
        const density = cached.values.get(agent.path.road.districtId) ?? 0.3;
        if (agent.budget > Math.min(0.95, density * 0.6)) continue;
        if (agent.walking && (personCount >= 180 || distance > 4000)) continue;
        if (!agent.walking && carCount >= 300) continue;
        const position = movingPosition(agent.path, time, agent.seed, agent.walking);
        if (
          Math.hypot(position.x - center[0], position.y - center[1]) > Math.max(750, distance * 0.9)
        )
          continue;
        const height =
          streetHeight(terrain, [position.x, position.y], agent.path.road.bridge) + 0.08;
        if (agent.walking) {
          const n = personCount++,
            s = Math.max(1, Math.min(1.8, distance / 1300));
          put(
            people.current,
            n,
            position.x,
            height + 0.9 * s,
            -position.y,
            0.46 * s,
            1.15 * s,
            0.34 * s,
            position.angle
          );
          put(
            heads.current,
            n,
            position.x,
            height + 1.62 * s,
            -position.y,
            0.22 * s,
            0.25 * s,
            0.22 * s
          );
          const swing = Math.sin(time * 7 + agent.seed * 20) * 0.18;
          for (let k = 0; k < 2; k++) {
            const side = (k ? 1 : -1) * 0.13 * s;
            const stride = (k ? 1 : -1) * swing;
            put(
              legs.current,
              n * 2 + k,
              position.x + Math.cos(position.angle) * side + Math.sin(position.angle) * stride,
              height + 0.28 * s,
              -position.y - Math.sin(position.angle) * side + Math.cos(position.angle) * stride,
              0.14 * s,
              0.56 * s,
              0.16 * s,
              position.angle
            );
          }
          color.set(PALETTE[Math.floor(agent.seed * PALETTE.length)]);
          people.current.setColorAt(n, color);
        } else {
          const n = carCount++,
            s = Math.max(1, Math.min(1.7, distance / 3500)),
            dx = Math.sin(position.angle),
            dz = Math.cos(position.angle);
          put(
            cars.current,
            n,
            position.x,
            height + 0.65 * s,
            -position.y,
            1.75 * s,
            0.8 * s,
            4.1 * s,
            position.angle
          );
          put(
            roofs.current,
            n,
            position.x,
            height + 1.22 * s,
            -position.y,
            1.5 * s,
            0.55 * s,
            2.2 * s,
            position.angle
          );
          for (let k = 0; k < 2; k++) {
            const side = (k ? 1 : -1) * 0.58 * s;
            put(
              fronts.current,
              n * 2 + k,
              position.x + dx * 2.1 * s + dz * side,
              height + 0.68 * s,
              -position.y + dz * 2.1 * s - dx * side,
              0.36 * s,
              0.22 * s,
              0.12 * s,
              position.angle
            );
            put(
              backs.current,
              n * 2 + k,
              position.x - dx * 2.1 * s + dz * side,
              height + 0.68 * s,
              -position.y - dz * 2.1 * s - dx * side,
              0.32 * s,
              0.19 * s,
              0.12 * s,
              position.angle
            );
          }
          color.set(PALETTE[Math.floor(agent.seed * PALETTE.length)]);
          cars.current.setColorAt(n, color);
        }
      }
    let lampCount = 0;
    if (distance < 8500)
      for (const lamp of streetlights) {
        const p = pathPosition(lamp.path, lamp.at, lamp.path.road.widthM / 2 + 0.7, 1);
        const height = streetHeight(terrain, [p.x, p.y], lamp.path.road.bridge);
        const n = lampCount++;
        put(poles.current, n, p.x, height + 3.7, -p.y, 0.14, 7.4, 0.14);
        put(lamps.current, n, p.x, height + 7.45, -p.y, 0.85, 0.22, 0.42);
        put(pools.current, n, p.x, height + 0.12, -p.y, 9, 0.025, 9);
      }
    for (const [ref, count] of [
      [cars, carCount],
      [roofs, carCount],
      [fronts, carCount * 2],
      [backs, carCount * 2],
      [people, personCount],
      [heads, personCount],
      [legs, personCount * 2],
      [poles, lampCount],
      [lamps, lampCount],
      [pools, lampCount],
    ] as const) {
      if (ref.current) {
        ref.current.count = count;
        ref.current.instanceMatrix.needsUpdate = true;
        if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true;
      }
    }
    if (glow.current) glow.current.emissiveIntensity = (light?.night.value ?? 0) * 3;
    if (pools.current) pools.current.visible = (light?.night.value ?? 0) > 0.15;
  }, -0.2);
  const box = (
    ref: React.RefObject<InstancedMesh | null>,
    size: number,
    material: React.ReactNode
  ) => (
    <instancedMesh
      ref={ref}
      args={[undefined, undefined, size]}
      frustumCulled={false}
      raycast={() => {}}
    >
      <boxGeometry args={[1, 1, 1]} />
      {material}
    </instancedMesh>
  );
  return (
    <group>
      {box(cars, LIMIT, <meshStandardMaterial roughness={0.5} />)}
      {box(roofs, LIMIT, <meshStandardMaterial color="#283b4c" roughness={0.3} />)}
      {box(
        fronts,
        LIMIT * 2,
        <meshStandardMaterial color="#fff4ce" emissive="#fff1b8" emissiveIntensity={2} />
      )}
      {box(
        backs,
        LIMIT * 2,
        <meshStandardMaterial color="#a5190e" emissive="#ff321c" emissiveIntensity={1.5} />
      )}
      {box(people, LIMIT, <meshStandardMaterial roughness={1} />)}
      <instancedMesh
        ref={heads}
        args={[undefined, undefined, LIMIT]}
        frustumCulled={false}
        raycast={() => {}}
      >
        <sphereGeometry args={[1, 6, 5]} />
        <meshStandardMaterial color="#bf9776" />
      </instancedMesh>
      {box(legs, LIMIT * 2, <meshStandardMaterial color="#2e3c48" />)}
      {box(poles, LIMIT, <meshStandardMaterial color="#46515a" />)}
      {box(lamps, LIMIT, <meshStandardMaterial ref={glow} color="#d5cab2" emissive="#ffc880" />)}
      <instancedMesh
        ref={pools}
        args={[undefined, undefined, LIMIT]}
        frustumCulled={false}
        raycast={() => {}}
      >
        <sphereGeometry args={[1, 12, 4]} />
        <meshBasicMaterial color="#d9af65" transparent opacity={0.11} depthWrite={false} />
      </instancedMesh>
    </group>
  );
});
