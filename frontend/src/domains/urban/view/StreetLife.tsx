import { memo, useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, MeshStandardMaterial, Object3D } from 'three';
import type { Street, UrbanTime, Population } from '../entity/urban';
import type { City } from '../../city/entity/city';
import type { Terrain } from '../../terrain/entity/terrain';
import { streetHeight } from '../service/streetGeometryService';
import {
  distanceToStreet,
  streetSpeed,
  pathPosition,
  stableSeed,
  streetPath,
} from '../service/streetLifeService';
import { displayDensity, populationAt } from '../service/populationService';
import type { LivePlace } from '../entity/liveUrban';
import { freshReading, livePlaceAt } from '../service/liveUrbanService';
import { urbanTime } from '../service/urbanTimeService';
import type { FloodField } from '../service/floodFieldService';
import { floodMotion, emptyFloodStats, type FloodStats } from '../service/floodMovementService';
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
  livePlaces,
  flood,
  onFloodStats,
  city,
  animate,
}: {
  roads: Street[];
  terrain: Terrain | null;
  center: [number, number];
  distance: number;
  clock: UrbanTime;
  population: Population | null;
  livePlaces: LivePlace[];
  flood: FloodField;
  onFloodStats?: (stats: FloodStats) => void;
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
  const arms = useRef<InstancedMesh>(null),
    signals = useRef<InstancedMesh>(null);
  const lastReport = useRef({ time: 0, key: '' });
  useEffect(() => () => onFloodStats?.(emptyFloodStats), [onFloodStats]);
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
            .flatMap((walking) => {
              const count = Math.min(
                24,
                Math.max(1, Math.floor(path.length / (walking ? 30 : 45)))
              );
              return Array.from({ length: count }, (_, i) => ({
                path,
                walking,
                queue: i * 6,
                reaction: {
                  key: '',
                  home: NaN,
                  travel: 0,
                  time: NaN,
                  arc: NaN,
                  direction: 1,
                  heading: 1,
                },
                seed: (i + 0.25 + stableSeed(path.road.id + ':' + walking + ':' + i) * 0.5) / count,
                budget: stableSeed(path.road.id + ':budget:' + walking + ':' + i),
              }));
            });
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
    if (animate || lastTime.current == null || (clock.current.historical && !clock.current.playing))
      lastTime.current = at / 1000;
    const time = lastTime.current;
    const now = Date.now();
    const currentPlaces = clock.current.historical
      ? []
      : livePlaces.map((place) => ({
          ...place,
          population: freshReading(place.population, now),
          traffic: freshReading(place.traffic, now),
        }));
    let carCount = 0,
      personCount = 0,
      signalCount = 0;
    const stats = { ...emptyFloodStats };
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
        const baseDirection =
          (!agent.walking && agent.path.road.oneway) || (agent.seed > 0.5 ? 1 : -1);
        const lane = agent.walking
          ? agent.path.road.motor
            ? agent.path.road.widthM / 2 + 0.7
            : 0
          : Math.min(2.5, agent.path.road.widthM * 0.23);
        const normalSpeed = streetSpeed(agent.path, agent.seed, agent.walking);
        const route = flood.route(agent.path, agent.walking, baseDirection);
        let home =
          baseDirection > 0 ? agent.seed * agent.path.length : (1 - agent.seed) * agent.path.length;
        let travel = Math.max(0, time - (clock.current.origin ?? 0) / 1000) * normalSpeed;
        let direction = baseDirection,
          speed = normalSpeed;
        if (!clock.current.historical) {
          const motion = agent.reaction;
          if (!Number.isFinite(motion.home) || motion.key !== flood.key) {
            const phase =
              (((time * normalSpeed + agent.seed * agent.path.length) % agent.path.length) +
                agent.path.length) %
              agent.path.length;
            motion.home = Number.isFinite(motion.arc)
              ? motion.arc
              : baseDirection > 0
                ? phase
                : agent.path.length - phase;
            motion.direction = Number.isFinite(motion.arc) ? motion.heading : baseDirection;
            motion.time = time;
            motion.travel = 0;
            motion.key = flood.key;
          }
          const previous = pathPosition(
            agent.path,
            Number.isFinite(motion.arc) ? motion.arc : motion.home,
            lane,
            baseDirection
          );
          const traffic = livePlaceAt(currentPlaces, previous.x, previous.y)?.traffic;
          if (!agent.walking && traffic) speed = traffic.speedKmh / 3.6;
          motion.travel += Math.max(0, Math.min(2, time - motion.time)) * speed;
          motion.time = time;
          home = motion.home;
          travel = motion.travel;
          direction = motion.direction;
        } else agent.reaction.home = agent.reaction.arc = NaN;
        const response = floodMotion(
          route,
          home,
          travel,
          direction,
          agent.walking,
          speed,
          agent.queue,
          normalSpeed
        );
        if (!clock.current.historical) {
          agent.reaction.arc = response.arc;
          agent.reaction.heading = response.direction;
        }
        const position = pathPosition(agent.path, response.arc, lane, baseDirection);
        if (response.direction !== baseDirection) position.angle += Math.PI;
        const place = clock.current.historical
          ? undefined
          : livePlaceAt(currentPlaces, position.x, position.y);
        const currentPopulation = place?.population;
        const density =
          currentPopulation && place
            ? displayDensity(
                (currentPopulation.minimum + currentPopulation.maximum) / 2,
                place.areaKm2
              )
            : (cached.values.get(agent.path.road.districtId) ?? 0.3);
        if (agent.budget > Math.min(0.95, density * 0.6)) continue;
        if (agent.walking && (personCount >= 180 || distance > 4000)) continue;
        if (!agent.walking && carCount >= 300) continue;
        if (
          Math.hypot(position.x - center[0], position.y - center[1]) > Math.max(750, distance * 0.9)
        )
          continue;
        const height =
          streetHeight(terrain, [position.x, position.y], agent.path.road.bridge) + 0.08;
        const affected = response.action !== 'moving';
        if (affected) {
          if (response.action === 'stranded') stats.stranded++;
          else if (response.action === 'exposed') stats.exposed++;
          else if (agent.walking) stats.avoiding++;
          else stats.stopped++;
          const red = response.action === 'stranded' || response.action === 'exposed';
          const pulse = 0.8 + 0.2 * Math.sin(time * 4);
          const s = Math.max(1, Math.min(5, distance / 600));
          put(
            signals.current,
            signalCount,
            position.x,
            height + Math.max(2.8, response.contact?.depth ?? 0) + s,
            -position.y,
            s * pulse,
            s * pulse,
            s * pulse
          );
          color.set(red ? '#ef5c44' : '#ffbd45');
          signals.current?.setColorAt(signalCount++, color);
        }
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
          const swing = response.moving ? Math.sin(time * 7 + agent.seed * 20) * 0.18 : 0;
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
          for (let k = 0; k < 2; k++) {
            const side = (k ? 1 : -1) * 0.36 * s,
              raised = response.action === 'stranded';
            put(
              arms.current,
              n * 2 + k,
              position.x + Math.cos(position.angle) * side,
              height + (raised ? 1.7 : 0.95) * s,
              -position.y - Math.sin(position.angle) * side,
              0.14 * s,
              0.65 * s,
              0.14 * s,
              position.angle
            );
          }
          color.set(
            affected
              ? response.action === 'stranded'
                ? '#e16b4c'
                : '#e7b14b'
              : PALETTE[Math.floor(agent.seed * PALETTE.length)]
          );
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
          const blink = affected && Math.sin(time * 5) > 0;
          color.set(affected ? (blink ? '#ffbd45' : '#9b441f') : '#fff4ce');
          fronts.current?.setColorAt(n * 2, color);
          fronts.current?.setColorAt(n * 2 + 1, color);
          color.set(affected ? (blink ? '#ffbd45' : '#b72c16') : '#a5190e');
          backs.current?.setColorAt(n * 2, color);
          backs.current?.setColorAt(n * 2 + 1, color);
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
      [arms, personCount * 2],
      [signals, signalCount],
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
    if (
      onFloodStats &&
      (!lastReport.current.key || !animate || performance.now() - lastReport.current.time > 500)
    ) {
      const key = JSON.stringify(stats);
      if (lastReport.current.key !== key) {
        lastReport.current = { time: performance.now(), key };
        onFloodStats(stats);
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
      {box(fronts, LIMIT * 2, <meshBasicMaterial toneMapped={false} />)}
      {box(backs, LIMIT * 2, <meshBasicMaterial toneMapped={false} />)}
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
      {box(arms, LIMIT * 2, <meshStandardMaterial color="#bf9776" />)}
      <instancedMesh
        ref={signals}
        args={[undefined, undefined, LIMIT * 2]}
        frustumCulled={false}
        raycast={() => {}}
      >
        <octahedronGeometry args={[1, 0]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
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
