import {
  useEffect,
  useMemo,
  useRef,
  useCallback,
  useState,
  memo,
  createContext,
  useContext,
} from 'react';
import type { ComponentRef } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import * as THREE from 'three';
import { requestBuildingMesh } from '../repository/buildingGeometryRepository';
import type { City, CityBuilding, CityFocus, CityTile } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import { watchContextLoss } from '../../catalog/service/sceneLifecycleService';
import { positionSceneLabels } from '../../catalog/service/sceneLabelService';

import type { SharedSite, SharedInstallation } from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import { buildingOpacity, otherDistrictOpacity } from '../service/siteVisibilityService';
import { buildingFaceIndex } from '../service/buildingSelectionService';
import type { FacilityType, Placement } from '../../game/entity/game';
import { FacilityMesh } from '../../catalog/view/FacilityMesh';
import { LiveRainScene } from '../../rainfall/view/LiveRainScene';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight, terrainLine } from '../../terrain/service/terrainService';
import { TerrainSurface } from '../../terrain/view/TerrainSurface';
const TerrainContext = createContext<Terrain | null>(null);
type CameraState = { center: [number, number]; distance: number };
function Buildings({
  buildings,
  opacity = 1,
  onSelect,
}: {
  buildings: CityBuilding[];
  opacity?: number;
  onSelect: (b: CityBuilding) => void;
}) {
  const terrain = useContext(TerrainContext);
  const [rendered, setRendered] = useState<{
    geometry: THREE.BufferGeometry;
    ends: number[];
    source: CityBuilding[];
  } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let geometry: THREE.BufferGeometry | undefined;
    if (buildings.length)
      void requestBuildingMesh(
        buildings.map((b) => ({ ...b, baseElevationM: terrainHeight(terrain, b.center) })),
        controller.signal
      )
        .then((data) => {
          if (controller.signal.aborted) return;
          geometry = new THREE.BufferGeometry();
          geometry.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
          geometry.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3));
          geometry.computeBoundingSphere();
          setRendered({ geometry, ends: data.ends, source: buildings });
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e);
        });
    return () => {
      controller.abort();
      geometry?.dispose();
    };
  }, [buildings, terrain]);
  if (error) throw error;
  const geometry = rendered?.source === buildings ? rendered.geometry : null;
  return geometry ? (
    <mesh
      geometry={geometry}
      rotation={[-Math.PI / 2, 0, 0]}
      onClick={(event) => {
        if (event.delta > 5 || event.faceIndex == null) return;
        const index = buildingFaceIndex(rendered!.ends, event.faceIndex);
        if (index >= 0) {
          event.stopPropagation();
          onSelect(buildings[index]);
        }
      }}
    >
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
const Surface = memo(function Surface({
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
});
function Lines({
  city,
  selected,
  ownDistrictId,
}: {
  city: City;
  selected: string;
  ownDistrictId: string | null;
}) {
  const terrain = useContext(TerrainContext);
  const geometry = useMemo(() => {
    const points: number[] = [];
    for (const d of city.districts)
      for (const polygon of d.polygons)
        for (const ring of polygon)
          terrainLine(terrain, ring, 8).forEach((value) => points.push(value));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    return g;
  }, [city, terrain]);
  const roads = useMemo(() => {
    const points: number[] = [];
    for (const road of city.roads)
      terrainLine(terrain, road.coordinates, 3).forEach((value) => points.push(value));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    return g;
  }, [city, terrain]);
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
      {district && !ownDistrictId && !terrain && (
        <Surface polygons={district.polygons} height={0.01} color="#cbd9bd" />
      )}
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
  const terrain = useContext(TerrainContext);
  const controls = useRef<ComponentRef<typeof OrbitControls> | null>(null),
    last = useRef(0);
  const { camera, gl, invalidate, size } = useThree();
  const report = useCallback(
    (force = false) => {
      if (!controls.current) return;
      const target = controls.current.target;
      const elevation = terrainHeight(terrain, [target.x, -target.z]);
      const rise = elevation - target.y;
      target.y = elevation;
      camera.position.y += rise;
      camera.position.y = Math.max(
        camera.position.y,
        terrainHeight(terrain, [camera.position.x, -camera.position.z]) + 15
      );
      const now = performance.now();
      if (!force && now - last.current < 350) return;
      last.current = now;
      onCamera({ center: [target.x, -target.z], distance: camera.position.distanceTo(target) });
    },
    [camera, onCamera, terrain]
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
    const elevation = terrainHeight(terrain, [x, y]);
    camera.position.set(x, elevation + distance * 0.8, -y + distance * 0.6);
    controls.current?.target.set(x, elevation, -y);
    controls.current?.update();
    report(true);
    invalidate();
  }, [camera, focus, bounds, size.width, size.height, invalidate, report, terrain]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      minDistance={180}
      maxDistance={150000}
      maxPolarAngle={Math.PI * 0.46}
      screenSpacePanning={false}
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
  const terrain = useContext(TerrainContext);
  const point = useMemo(() => new THREE.Vector3(), []);
  const last = useRef('');
  const dirty = useRef(true);
  useEffect(() => {
    dirty.current = true;
  }, [city, regions, labels, near, selected, terrain]);
  useFrame(({ camera, size }) => {
    const signature = `${camera.matrixWorld.elements.join(',')}:${camera.projectionMatrix.elements.join(',')}:${size.width}:${size.height}:${labels.size}`;
    if (!dirty.current && last.current === signature) return;
    dirty.current = false;
    last.current = signature;
    const candidates = [];
    for (const element of labels.values()) element.style.display = 'none';
    const locations = near
      ? regions.map((r) => ({ id: r.mapId, districtId: r.districtId, center: r.center }))
      : city.districts.map((d) => ({ ...d, districtId: d.id }));
    for (const location of locations) {
      point
        .set(location.center[0], terrainHeight(terrain, location.center) + 60, -location.center[1])
        .project(camera);
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
  terrain,
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
  preview,
  onBuilding,
  eligibleRoofs,
  occupiedRoofs,
  facilityType,
  viewerId,
}: {
  terrain: Terrain | null;
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
  preview: { site: SharedSite; placement: Placement } | null;
  onBuilding: (districtId: string, b: CityBuilding) => void;
  eligibleRoofs: ReadonlySet<string>;
  occupiedRoofs: ReadonlySet<string>;
  facilityType: FacilityType | '';
  viewerId: string | null;
}) {
  const overviewIds = useMemo(() => new Set(city.overviewBuildings.map((b) => b.id)), [city]);
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 1.5]}
      camera={{ position: [0, 30000, 22000], near: 5, far: 250000, fov: 45 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
    >
      <TerrainContext.Provider value={terrain}>
        <color attach="background" args={['#e8e9dd']} />
        <ambientLight intensity={1.5} />
        <directionalLight position={[-20000, 30000, 10000]} intensity={2.2} />
        {terrain ? (
          <TerrainSurface terrain={terrain} ownDistrictId={ownDistrictId} selected={selected} />
        ) : ownDistrictId ? (
          city.districts.map((d) => (
            <Surface
              key={d.id}
              polygons={d.polygons}
              color={d.id === ownDistrictId ? '#a3c884' : '#bccbb0'}
              opacity={d.id === ownDistrictId ? 1 : otherDistrictOpacity}
            />
          ))
        ) : (
          <Surface polygons={city.boundary} color="#dfe3cf" />
        )}
        <Lines city={city} selected={selected} ownDistrictId={ownDistrictId} />
        {!terrain &&
          city.surfaces.map((s, i) => (
            <Surface
              key={i}
              polygons={s.polygons}
              color={s.kind === 'water' ? '#81b1ba' : '#b4c8a3'}
              height={s.kind === 'water' ? 4 : 2}
            />
          ))}
        <DistrictBuildings
          facilityType={facilityType}
          eligibleRoofs={eligibleRoofs}
          occupiedRoofs={occupiedRoofs}
          buildings={city.overviewBuildings}
          city={city}
          ownDistrictId={ownDistrictId}
          onBuilding={onBuilding}
        />
        {tiles.map((t) => (
          <DetailBuildings
            exclude={overviewIds}
            facilityType={facilityType}
            key={t.id}
            eligibleRoofs={eligibleRoofs}
            occupiedRoofs={occupiedRoofs}
            buildings={t.buildings}
            onBuilding={onBuilding}
            city={city}
            ownDistrictId={ownDistrictId}
          />
        ))}
        {ownDistrictId &&
          city.districts
            .find((d) => d.id === ownDistrictId)
            ?.polygons.flatMap((p, i) =>
              p.map((ring, j) => (
                <Line
                  key={`${i}:${j}`}
                  segments
                  points={terrainLine(terrain, ring, 8).reduce<[number, number, number][]>(
                    (out, value, index, values) => {
                      if (index % 3 === 0) out.push([value, values[index + 1], values[index + 2]]);
                      return out;
                    },
                    []
                  )}
                  color="#345d35"
                  lineWidth={2.6}
                />
              ))
            )}
        {sites
          .filter(
            (site) =>
              site.districtId === selected ||
              installations.some((i) => siteKey(i) === siteKey(site))
          )
          .map((site) => {
            const installed = installations.find((i) => siteKey(i) === siteKey(site));
            const opacity = buildingOpacity(
              (!facilityType || site.allowedTypes.includes(facilityType)) &&
                (!installed || installed.ownerId === viewerId),
              !!ownDistrictId && site.districtId !== ownDistrictId
            );
            return (
              <group key={siteKey(site)}>
                <SiteSurface
                  site={site}
                  color={
                    site.districtId === selected && site.cellId === selectedSite
                      ? '#ffd56d'
                      : installed
                        ? '#367c51'
                        : site.kind === 'ROOF'
                          ? '#d9d8cb'
                          : '#b6c3ab'
                  }
                  opacity={opacity}
                  onClick={() => onSite(siteKey(site))}
                />
                {installed && (
                  <FacilityMesh
                    cell={{
                      ...site,
                      heightM:
                        terrainHeight(terrain, site.center) +
                        (site.kind === 'ROOF' ? site.heightM : 0.2),
                    }}
                    placement={installed}
                    preview={false}
                    opacity={opacity}
                    onSelect={() => onSite(siteKey(site))}
                  />
                )}
              </group>
            );
          })}
        {preview && (
          <FacilityMesh
            cell={{
              ...preview.site,
              heightM:
                terrainHeight(terrain, preview.site.center) +
                (preview.site.kind === 'ROOF' ? preview.site.heightM : 0.2),
            }}
            placement={preview.placement}
            preview
            opacity={
              !ownDistrictId || preview.site.districtId === ownDistrictId ? 1 : otherDistrictOpacity
            }
            onSelect={() => onSite(siteKey(preview.site))}
          />
        )}
        {installations
          .filter((i) => !sites.some((s) => siteKey(s) === siteKey(i)))
          .map((i) => (
            <mesh
              key={i.id}
              position={[
                i.center[0],
                terrainHeight(terrain, i.center) + i.heightM + 3,
                -i.center[1],
              ]}
              onClick={(e) => {
                e.stopPropagation();
                onSite(siteKey(i));
              }}
            >
              <sphereGeometry
                args={[Math.max(2, Math.min(80, rainCamera.distance * 0.004)), 8, 6]}
              />
              <meshStandardMaterial
                color="#327b4f"
                transparent
                opacity={buildingOpacity(
                  (!facilityType || i.facilityType === facilityType) && i.ownerId === viewerId,
                  !!ownDistrictId && i.districtId !== ownDistrictId
                )}
              />
            </mesh>
          ))}
        <LiveRainScene
          districts={wetDistricts}
          center={rainCamera.center}
          distance={rainCamera.distance}
          animate={animateRain}
          terrain={terrain}
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
      </TerrainContext.Provider>
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
  const terrain = useContext(TerrainContext);
  const polygons = useMemo(() => [[site.coordinates]], [site]);
  return (
    <Surface
      polygons={polygons}
      height={
        terrainHeight(terrain, site.center) + (site.kind === 'ROOF' ? site.heightM : 0.2) + 0.1
      }
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
  onBuilding,
  eligibleRoofs,
  occupiedRoofs,
  facilityType,
}: {
  buildings: CityBuilding[];
  city: City;
  ownDistrictId: string | null;
  onBuilding: (districtId: string, b: CityBuilding) => void;
  eligibleRoofs: ReadonlySet<string>;
  occupiedRoofs: ReadonlySet<string>;
  facilityType: FacilityType | '';
}) {
  function selectBuilding(b: CityBuilding) {
    const district = city.districts.find((d) =>
      d.polygons.some(
        (p) => inRing(b.center, p[0]) && !p.slice(1).some((hole) => inRing(b.center, hole))
      )
    );
    if (district) onBuilding(district.id, b);
  }
  const groups = useMemo(() => {
    const district = city.districts.find((d) => d.id === ownDistrictId);
    const buckets = new Map<
      string,
      { eligible: boolean; other: boolean; buildings: CityBuilding[] }
    >();
    for (const b of buildings) {
      const other =
        !!district &&
        !district.polygons.some(
          (p) => inRing(b.center, p[0]) && !p.slice(1).some((h) => inRing(b.center, h))
        );
      const eligible = eligibleRoofs.has(b.id) && !occupiedRoofs.has(b.id);
      const key = `${eligible}:${other}`;
      if (!buckets.has(key)) buckets.set(key, { eligible, other, buildings: [] });
      buckets.get(key)!.buildings.push(b);
    }
    return [...buckets.entries()];
  }, [buildings, city, ownDistrictId, eligibleRoofs, occupiedRoofs]);
  return (
    <>
      {groups.map(([key, values]) => (
        <Buildings
          key={key}
          buildings={values.buildings}
          opacity={buildingOpacity(
            values.eligible && (!facilityType || facilityType === 'GREEN_ROOF'),
            values.other
          )}
          onSelect={selectBuilding}
        />
      ))}
    </>
  );
}

function DetailBuildings({
  exclude,
  ...props
}: React.ComponentProps<typeof DistrictBuildings> & { exclude: ReadonlySet<string> }) {
  const buildings = useMemo(
    () => props.buildings.filter((b) => !exclude.has(b.id)),
    [props.buildings, exclude]
  );
  return <DistrictBuildings {...props} buildings={buildings} />;
}
