import { useEffect, useMemo, useRef, useCallback } from 'react';
import type { ComponentRef } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import type { City, CityBuilding, CityFocus, CityTile } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import { watchContextLoss } from '../../catalog/service/sceneLifecycleService';
import { positionSceneLabels } from '../../catalog/service/sceneLabelService';

import type { SharedSite, SharedInstallation } from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import { LiveRainScene } from '../../rainfall/view/LiveRainScene';
type CameraState = { center: [number, number]; distance: number };
function Buildings({ buildings, opacity = 1 }: { buildings: CityBuilding[]; opacity?: number }) {
  const geometry = useMemo(() => {
    const parts = buildings.map(
      (b) =>
        new THREE.ExtrudeGeometry(polygonShapes(b.polygons), {
          depth: b.heightM,
          bevelEnabled: false,
          steps: 1,
        })
    );
    const combined = parts.length ? mergeGeometries(parts, false) : null;
    parts.forEach((p) => p.dispose());
    return combined;
  }, [buildings]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  return geometry ? (
    <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]}>
      <meshStandardMaterial
        color="#d9d8cb"
        roughness={0.85}
        transparent={opacity < 1}
        opacity={opacity}
        depthWrite={opacity === 1}
      />
    </mesh>
  ) : null;
}
function Surface({
  polygons,
  color,
  height = 0,
  opacity = 1,
  onClick,
}: {
  polygons: City['boundary'];
  color: string;
  height?: number;
  opacity?: number;
  onClick?: () => void;
}) {
  const geometry = useMemo(() => new THREE.ShapeGeometry(polygonShapes(polygons)), [polygons]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh
      geometry={geometry}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, height, 0]}
      onClick={
        onClick
          ? (event) => {
              event.stopPropagation();
              onClick();
            }
          : undefined
      }
    >
      <meshStandardMaterial
        color={color}
        side={THREE.DoubleSide}
        roughness={1}
        transparent={opacity < 1}
        opacity={opacity}
        depthWrite={opacity === 1}
      />
    </mesh>
  );
}
function Lines({ city, selected }: { city: City; selected: string }) {
  const geometry = useMemo(() => {
    const points: number[] = [];
    for (const d of city.districts)
      for (const polygon of d.polygons)
        for (const ring of polygon)
          for (let i = 1; i < ring.length; i++)
            points.push(ring[i - 1][0], 8, -ring[i - 1][1], ring[i][0], 8, -ring[i][1]);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    return g;
  }, [city]);
  const roads = useMemo(() => {
    const points: number[] = [];
    for (const r of city.roads)
      for (let i = 1; i < r.coordinates.length; i++)
        points.push(
          r.coordinates[i - 1][0],
          3,
          -r.coordinates[i - 1][1],
          r.coordinates[i][0],
          3,
          -r.coordinates[i][1]
        );
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    return g;
  }, [city]);
  useEffect(
    () => () => {
      geometry.dispose();
      roads.dispose();
    },
    [geometry, roads]
  );
  const district = city.districts.find((d) => d.id === selected);
  return (
    <>
      <lineSegments geometry={roads}>
        <lineBasicMaterial color="#bfc3b4" transparent opacity={0.65} />
      </lineSegments>
      <lineSegments geometry={geometry}>
        <lineBasicMaterial color="#889b81" transparent opacity={0.65} />
      </lineSegments>
      {district && <Surface polygons={district.polygons} height={0.01} color="#cbd9bd" />}
    </>
  );
}
function Controls({
  focus,
  bounds,
  onCamera,
  onUnavailable,
}: {
  focus: CityFocus;
  bounds: City['bounds'];
  onCamera: (state: CameraState) => void;
  onUnavailable: () => void;
}) {
  const controls = useRef<ComponentRef<typeof OrbitControls> | null>(null),
    last = useRef(0);
  const { camera, gl, invalidate, size } = useThree();
  const report = useCallback(
    (force = false) => {
      if (!controls.current) return;
      const now = performance.now();
      if (!force && now - last.current < 350) return;
      last.current = now;
      const target = controls.current.target;
      onCamera({ center: [target.x, -target.z], distance: camera.position.distanceTo(target) });
    },
    [camera, onCamera]
  );
  useEffect(() => watchContextLoss(gl.domElement, onUnavailable), [gl, onUnavailable]);
  useEffect(() => {
    let [x, y] = focus.center;
    let distance = focus.distance;
    if (focus.overview && camera instanceof THREE.PerspectiveCamera) {
      x = (bounds[0] + bounds[2]) / 2;
      y = (bounds[1] + bounds[3]) / 2;
      const halfWidth = (bounds[2] - bounds[0]) / 2;
      const halfHeight = (bounds[3] - bounds[1]) / 2;
      const tangent = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * 0.88;
      distance =
        Math.max(halfWidth / ((tangent * size.width) / size.height), (halfHeight * 0.8) / tangent) +
        halfHeight * 0.6;
    }
    camera.position.set(x, distance * 0.8, -y + distance * 0.6);
    controls.current?.target.set(x, 0, -y);
    controls.current?.update();
    report(true);
    invalidate();
  }, [camera, focus, bounds, size.width, size.height, invalidate, report]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      minDistance={180}
      maxDistance={150000}
      maxPolarAngle={Math.PI * 0.46}
      enableDamping
      dampingFactor={0.12}
      onChange={() => report()}
      onEnd={() => report(true)}
    />
  );
}
function ProjectedLabels({
  city,
  regions,
  labels,
  near,
  selected,
}: {
  city: City;
  regions: CityPlayRegion[];
  labels: Map<string, HTMLElement>;
  near: boolean;
  selected: string;
}) {
  const point = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    const candidates = [];
    for (const element of labels.values()) element.style.display = 'none';
    const locations = near
      ? regions.map((r) => ({ id: r.mapId, districtId: r.districtId, center: r.center }))
      : city.districts.map((d) => ({ ...d, districtId: d.id }));
    for (const location of locations) {
      point.set(location.center[0], 60, -location.center[1]).project(camera);
      if (Math.abs(point.x) > 1 || Math.abs(point.y) > 1 || Math.abs(point.z) > 1) continue;
      candidates.push({
        id: location.id,
        x: ((point.x + 1) * size.width) / 2,
        y: ((1 - point.y) * size.height) / 2,
        width: near ? 136 : 80,
        height: near ? 30 : 26,
        priority: location.districtId === selected ? 2 : 0,
      });
    }
    for (const label of positionSceneLabels(candidates, {
      left: 12,
      top: 130,
      right: size.width - 12,
      bottom: size.height - 110,
    })) {
      const element = labels.get(label.id);
      if (!element) continue;
      element.style.display = 'block';
      element.style.transform = `translate(${label.x}px,${label.y}px) translate(-50%,-50%)`;
    }
  });
  return null;
}
export default function CityScene({
  city,
  regions,
  tiles,
  focus,
  selected,
  near,
  onCamera,
  labels,
  onUnavailable,
  ownDistrictId,
  sites,
  installations,
  selectedSite,
  onSite,
  wetDistricts,
  rainCamera,
  animateRain,
}: {
  city: City;
  regions: CityPlayRegion[];
  tiles: CityTile[];
  focus: CityFocus;
  selected: string;
  near: boolean;
  onCamera: (state: CameraState) => void;
  labels: Map<string, HTMLElement>;
  onUnavailable: () => void;
  ownDistrictId: string | null;
  sites: SharedSite[];
  installations: SharedInstallation[];
  selectedSite: string;
  onSite: (key: string) => void;
  wetDistricts: City['districts'];
  rainCamera: CameraState;
  animateRain: boolean;
}) {
  const overview = useMemo(() => {
    const loaded = new Set(tiles.flatMap((t) => t.buildings.map((b) => b.id)));
    return city.overviewBuildings.filter((b) => !loaded.has(b.id));
  }, [city, tiles]);
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 1.5]}
      camera={{ position: [0, 30000, 22000], near: 5, far: 250000, fov: 45 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
    >
      <color attach="background" args={['#e8e9dd']} />
      <ambientLight intensity={1.5} />
      <directionalLight position={[-20000, 30000, 10000]} intensity={2.2} />
      <Surface polygons={city.boundary} color="#dfe3cf" />
      <Lines city={city} selected={selected} />
      {city.surfaces.map((s, i) => (
        <Surface
          key={i}
          polygons={s.polygons}
          color={s.kind === 'water' ? '#81b1ba' : '#b4c8a3'}
          height={s.kind === 'water' ? 4 : 2}
        />
      ))}
      <DistrictBuildings buildings={overview} city={city} ownDistrictId={ownDistrictId} />
      {tiles.map((t) => (
        <DistrictBuildings
          key={t.id}
          buildings={t.buildings}
          city={city}
          ownDistrictId={ownDistrictId}
        />
      ))}
      {ownDistrictId &&
        city.districts.map((d) => (
          <Surface
            key={d.id}
            polygons={d.polygons}
            height={0.02}
            color={d.id === ownDistrictId ? '#b3d29a' : '#f8f8ef'}
            opacity={d.id === ownDistrictId ? 0.8 : 0.3}
          />
        ))}
      {sites
        .filter(
          (site) =>
            site.districtId === selected || installations.some((i) => siteKey(i) === siteKey(site))
        )
        .map((site) => {
          const installed = installations.some((i) => siteKey(i) === siteKey(site));
          return (
            <SiteSurface
              key={siteKey(site)}
              site={site}
              color={
                site.districtId === selected && site.cellId === selectedSite
                  ? '#ffd56d'
                  : installed
                    ? '#367c51'
                    : '#d4b46d'
              }
              opacity={!ownDistrictId || site.districtId === ownDistrictId ? 1 : 0.35}
              onClick={() => onSite(siteKey(site))}
            />
          );
        })}
      <LiveRainScene
        districts={wetDistricts}
        center={rainCamera.center}
        distance={rainCamera.distance}
        animate={animateRain}
      />
      <ProjectedLabels
        city={city}
        regions={regions}
        labels={labels}
        near={near}
        selected={selected}
      />
      <Controls
        focus={focus}
        bounds={city.bounds}
        onCamera={onCamera}
        onUnavailable={onUnavailable}
      />
    </Canvas>
  );
}

function SiteSurface({
  site,
  color,
  opacity,
  onClick,
}: {
  site: SharedSite;
  color: string;
  opacity: number;
  onClick: () => void;
}) {
  const polygons = useMemo(() => [[site.coordinates]], [site]);
  return (
    <Surface
      polygons={polygons}
      height={site.heightM + 0.8}
      color={color}
      opacity={opacity}
      onClick={onClick}
    />
  );
}
function inRing([x, y]: [number, number], ring: [number, number][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [a, b] = ring[i],
      [c, d] = ring[j];
    if (b > y !== d > y && x < ((c - a) * (y - b)) / (d - b) + a) inside = !inside;
  }
  return inside;
}
function DistrictBuildings({
  buildings,
  city,
  ownDistrictId,
}: {
  buildings: CityBuilding[];
  city: City;
  ownDistrictId: string | null;
}) {
  const groups = useMemo(() => {
    const district = city.districts.find((d) => d.id === ownDistrictId);
    if (!district) return [buildings, []];
    const own: CityBuilding[] = [],
      other: CityBuilding[] = [];
    for (const b of buildings) {
      const match = district.polygons.some(
        (p) => inRing(b.center, p[0]) && !p.slice(1).some((hole) => inRing(b.center, hole))
      );
      (match ? own : other).push(b);
    }
    return [own, other];
  }, [buildings, city, ownDistrictId]);
  return (
    <>
      <Buildings buildings={groups[0]} />
      <Buildings buildings={groups[1]} opacity={0.3} />
    </>
  );
}
