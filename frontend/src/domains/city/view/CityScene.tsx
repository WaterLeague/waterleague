import { scenePointer, clearScenePointer } from '../service/mapCursor';
import { WatershedMapMesh } from '../../watershed/view/WatershedMapMesh';
import type { WatershedMapSelection } from '../../watershed/service/watershedMap';
import type { AudioHandle } from '../../audio/entity/audio';
import { CityAudioListener } from '../../audio/view/CityAudioListener';
import { GroundCandidates } from '../../installation/view/GroundCandidates';
import type { GroundCandidate } from '../../installation/service/candidateTilesService';
import { candidateSurfaceLift } from '../../terrain/service/surfaceDisplayService';
import { pavementGeometry } from '../../catalog/service/pavementGeometryService';
import { placementFootprint } from '../../catalog/service/facilityGeometryService';
import { InstallationSymbols } from '../../installation/view/InstallationSymbols';
import { InstallationNameplates } from '../../installation/view/InstallationNameplates';
import { installationSymbols } from '../../installation/service/installationSymbolsService';
import type { PublicFrame } from '../../surface/service/publicSurfaceService';
import { publicInfrastructureBuildingIds } from '../../infrastructure/service/infrastructureService';
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
import { Canvas, events, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import * as THREE from 'three';
import { requestBuildingMesh } from '../repository/buildingGeometryRepository';
import { buildingRaycast } from '../service/buildingRaycastService';
import type { City, CityBuilding, CityFocus, CityTile } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import { watchContextLoss } from '../../catalog/service/sceneLifecycleService';
import { labelLeaderEnd, positionSceneLabels } from '../../catalog/service/sceneLabelService';
import { positionDistrictLabels } from '../service/districtLabelService';
import { districtLabelBounds, overviewCamera } from '../service/overviewCameraService';

import type {
  SharedSite,
  SharedInstallation,
  InstallationLayout,
} from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import {
  buildingOpacity,
  otherDistrictOpacity,
  siteAppearance,
} from '../service/siteVisibilityService';
import {
  cisternSiteColors,
  type CisternSiteRole,
} from '../../installation/service/cisternPlanService';
import { buildingFaceIndex } from '../service/buildingSelectionService';
import { detailLabelDistance } from '../service/cityService';
import type { FacilityType, Placement } from '../../game/entity/game';
import { FacilityMesh } from '../../catalog/view/FacilityMesh';
import { LiveRainScene } from '../../rainfall/view/LiveRainScene';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight, terrainLine } from '../../terrain/service/terrainService';
import { buildingBaseElevation } from '../service/buildingElevationService';
import { TerrainSurface } from '../../terrain/view/TerrainSurface';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { InfrastructureMarkers } from '../../infrastructure/view/InfrastructureMarkers';
import { InfrastructureFootprints } from '../../infrastructure/view/InfrastructureFootprints';
import type { TraceTile } from '../../floodtrace/entity/floodTrace';
import { FloodTraceLayer } from '../../floodtrace/view/FloodTraceLayer';
import { SurfaceLayer } from '../../surface/view/SurfaceLayer';
import type { SurfaceFrame, SurfaceMetric } from '../../surface/entity/surface';
import { CisternLayoutMesh } from '../../installation/view/CisternLayoutMesh';
import { RiverLayer } from '../../surface/view/RiverLayer';
import { WaterScene } from '../../surface/view/WaterScene';
import { calmWater, type WaterWeather } from '../../surface/service/waterAppearanceService';
import type { CisternMapPreview } from '../../installation/dto/cisternLayoutDto';
import { createFloodField } from '../../urban/service/floodFieldService';
import type { FloodStats } from '../../urban/service/floodMovementService';
import type { LivePlace } from '../../urban/entity/liveUrban';
import type { Street, UrbanTime, Population } from '../../urban/entity/urban';
import { UrbanEnvironment } from '../../urban/view/UrbanEnvironment';
import { BuildingMaterial } from '../../urban/view/BuildingMaterial';
import { StreetLayer } from '../../urban/view/StreetLayer';
import {
  mapNearPlane,
  minimumMapDistance,
  minimumGroundClearance,
} from '../service/cameraDepthService';
import { StreetLife } from '../../urban/view/StreetLife';
import { RailLife } from '../../urban/view/RailLife';
import { ParkingLayer } from '../../urban/view/ParkingLayer';
import type { ParkingData } from '../../urban/entity/parking';
import { useParkingLots } from '../../urban/controller/useParkingLots';
import { emptyFloodStats } from '../../urban/service/floodMovementService';
import { CityOverview } from './CityOverview';
import { useServerConnected } from '../../../shared/controller/serverConnectionContext';
import { TopographyLayer } from '../../topography/view/TopographyLayer';
import { TopographyLabels } from '../../topography/view/TopographyLabels';
import type { TopographyView } from '../../topography/entity/topography';
const TerrainContext = createContext<Terrain | null>(null);
const mapEvents: Parameters<typeof Canvas>[0]['events'] = (state) => ({
  ...events(state),
  // 화면 위에 그린 참고 표식은 뒤쪽 건물의 클릭 차단보다 먼저 처리한다.
  filter: (items) =>
    items.sort(
      (a, b) =>
        2 * Number(b.object.userData.watershedSelection === true) -
        2 * Number(a.object.userData.watershedSelection === true) +
        Number(
          b.object.userData.publicAssetMarker === true ||
            b.object.userData.installationMarker === true
        ) -
        Number(
          a.object.userData.publicAssetMarker === true ||
            a.object.userData.installationMarker === true
        )
    ),
});
type CameraState = Pick<CityFocus, 'center' | 'distance' | 'heightM'>;
function Buildings({
  buildings,
  opacity = 1,
  available = false,
  onSelect,
}: {
  buildings: CityBuilding[];
  opacity?: number;
  available?: boolean;
  onSelect: (b: CityBuilding) => void;
}) {
  const terrain = useContext(TerrainContext);
  const [rendered, setRendered] = useState<{
    geometry: THREE.BufferGeometry;
    ends: number[];
    source: CityBuilding[];
    raycast: THREE.Mesh['raycast'];
  } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (!buildings.length) setRendered(null);
    else
      void requestBuildingMesh(
        buildings.map((b) => ({
          ...b,
          baseElevationM: buildingBaseElevation(terrain, b.polygons),
        })),
        controller.signal
      )
        .then((data) => {
          if (controller.signal.aborted) return;
          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
          geometry.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3));
          geometry.computeBoundingSphere();
          geometry.computeBoundingBox();
          setRendered({
            geometry,
            ends: data.ends,
            source: buildings,
            raycast: buildingRaycast(data),
          });
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e);
        });
    return () => {
      controller.abort();
    };
  }, [buildings, terrain]);
  // 대체 메시가 준비된 뒤 이전 GPU 버퍼를 해제해 비어 있는 프레임을 만들지 않는다.
  useEffect(() => () => rendered?.geometry.dispose(), [rendered]);
  if (error) throw error;
  const geometry = rendered?.geometry;
  return geometry ? (
    <mesh
      geometry={geometry}
      castShadow
      receiveShadow
      onPointerMove={(event) => scenePointer(event, available ? 'install' : 'inspect')}
      onPointerOut={clearScenePointer}
      raycast={rendered!.raycast}
      rotation={[-Math.PI / 2, 0, 0]}
      onClick={(event) => {
        if (event.delta > 5 || event.faceIndex == null) return;
        const index = buildingFaceIndex(rendered!.ends, event.faceIndex);
        if (index >= 0) {
          event.stopPropagation();
          onSelect(rendered!.source[index]);
        }
      }}
    >
      <BuildingMaterial opacity={opacity} available={available} />
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
  useEffect(
    () => () => {
      geometry.dispose();
    },
    [geometry]
  );
  const district = city.districts.find((d) => d.id === selected);
  return (
    <>
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
  onNavigate,
  onUnavailable,
  onOverview,
}: {
  focus: CityFocus;
  bounds: City['bounds'];
  onCamera: (state: CameraState) => void;
  onNavigate: (state: CameraState) => void;
  onUnavailable: () => void;
  onOverview: (value: boolean) => void;
}) {
  const terrain = useContext(TerrainContext);
  const controls = useRef<ComponentRef<typeof OrbitControls> | null>(null),
    reportTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appliedFocus = useRef<number | null>(null);
  const { camera, gl, invalidate, size } = useThree();
  const report = useCallback(
    (force = false) => {
      if (!controls.current) return;
      const target = controls.current.target;
      const elevation = terrainHeight(terrain, [target.x, -target.z]) + (focus.heightM ?? 0);
      const rise = elevation - target.y;
      target.y = elevation;
      camera.position.y += rise;
      camera.position.y = Math.max(
        camera.position.y,
        terrainHeight(terrain, [camera.position.x, -camera.position.z]) + minimumGroundClearance
      );
      if (camera instanceof THREE.PerspectiveCamera) {
        // 서울 축척에서도 도로와 얕은 수면의 깊이 차이가 버퍼에서 소실되지 않게 한다.
        const clearance =
          camera.position.y - terrainHeight(terrain, [camera.position.x, -camera.position.z]);
        const near = mapNearPlane(camera.position.distanceTo(target), clearance);
        if (Math.abs(camera.near - near) > 0.01) {
          camera.near = near;
          camera.updateProjectionMatrix();
        }
      }
      if (reportTimer.current) clearTimeout(reportTimer.current);
      const state: CameraState = {
        center: [target.x, -target.z],
        distance: camera.position.distanceTo(target),
        heightM: focus.heightM,
      };
      onNavigate(state);
      if (force) onCamera(state);
      else
        reportTimer.current = setTimeout(() => {
          reportTimer.current = null;
          onCamera(state);
        }, 180);
    },
    [camera, onCamera, onNavigate, terrain, focus.heightM]
  );
  useEffect(
    () => () => {
      if (reportTimer.current) clearTimeout(reportTimer.current);
    },
    []
  );
  useEffect(() => watchContextLoss(gl.domElement, onUnavailable), [gl, onUnavailable]);
  useEffect(() => {
    // 패널 크기 변경이나 지형 로딩으로 사용자가 보고 있던 위치를 초기화하지 않는다.
    if (appliedFocus.current === focus.key) {
      report(true);
      invalidate();
      return;
    }
    appliedFocus.current = focus.key;
    onOverview(focus.overview === true);
    let [x, y] = focus.center;
    let distance = focus.distance;
    if (focus.overview && camera instanceof THREE.PerspectiveCamera) {
      const area = districtLabelBounds(
        gl.domElement.closest('.city-stage'),
        size.width,
        size.height
      );
      // 전체 보기의 지도와 라벨을 조작부·예산창 사이에 맞춘다.
      const view = overviewCamera(bounds, size.width, size.height, camera.fov, {
        left: area.left + 28,
        right: area.right - 28,
        top: area.top + 22,
        bottom: area.bottom - 22,
      });
      [x, y] = view.center;
      distance = view.distance;
    }
    const elevation = terrainHeight(terrain, [x, y]) + (focus.heightM ?? 0);
    if (focus.preserveAngle && controls.current) {
      const direction = camera.position.clone().sub(controls.current.target).normalize();
      camera.position.set(x, elevation, -y).addScaledVector(direction, distance);
    } else {
      camera.position.set(x, elevation + distance * 0.8, -y + distance * 0.6);
    }
    controls.current?.target.set(x, elevation, -y);
    controls.current?.update();
    report(true);
    invalidate();
  }, [camera, focus, bounds, size.width, size.height, invalidate, report, terrain, onOverview, gl]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      minDistance={minimumMapDistance}
      maxDistance={350000}
      maxPolarAngle={Math.PI * 0.46}
      screenSpacePanning={false}
      enableDamping
      dampingFactor={0.12}
      onStart={() => onOverview(false)}
      onChange={() => report()}
      onEnd={() => report()}
    />
  );
}
function ProjectedLabels({
  city,
  regions,
  labels,
  selected,
  overview,
}: {
  city: City;
  regions: CityPlayRegion[];
  labels: Map<string, HTMLElement>;
  selected: string;
  overview: boolean;
}) {
  const terrain = useContext(TerrainContext);
  const invalidate = useThree((s) => s.invalidate);
  const controls = useThree((s) => s.controls) as ComponentRef<typeof OrbitControls> | null;
  const point = useMemo(() => new THREE.Vector3(), []);
  const last = useRef('');
  const dirty = useRef(true);
  useEffect(() => {
    dirty.current = true;
    invalidate();
  }, [city, regions, labels, selected, terrain, controls, overview, invalidate]);
  useEffect(() => {
    const layer = labels.values().next().value?.parentElement;
    if (!layer) return;
    const observer = new MutationObserver(() => {
      dirty.current = true;
      invalidate();
    });
    observer.observe(layer, { subtree: true, childList: true, characterData: true });
    return () => observer.disconnect();
  }, [labels, invalidate]);
  useFrame(({ camera, size }) => {
    const signature = `${camera.matrixWorld.elements.join(',')}:${camera.projectionMatrix.elements.join(',')}:${size.width}:${size.height}:${labels.size}`;
    if (!dirty.current && last.current === signature) return;
    dirty.current = false;
    last.current = signature;
    const candidates = [];
    for (const element of labels.values()) element.style.display = 'none';
    const distance = controls ? camera.position.distanceTo(controls.target) : Infinity;
    if (!overview && distance < detailLabelDistance) return;
    const near = !overview && distance < 9000;
    const locations = near
      ? regions.map((r) => ({ id: r.mapId, districtId: r.districtId, center: r.center }))
      : city.districts.map((d) => ({ ...d, districtId: d.id }));
    for (const location of locations) {
      point
        .set(location.center[0], terrainHeight(terrain, location.center) + 60, -location.center[1])
        .project(camera);
      if (!overview && (Math.abs(point.x) > 1 || Math.abs(point.y) > 1 || Math.abs(point.z) > 1))
        continue;
      const element = labels.get(location.id);
      if (!element) continue;
      element.style.display = 'block';
      element.title = element.textContent ?? '';
      element.classList.remove('is-compact');
      candidates.push({
        id: location.id,
        x: ((point.x + 1) * size.width) / 2,
        y: ((1 - point.y) * size.height) / 2,
        width: 0,
        height: 0,
        priority: location.districtId === selected ? 2 : 0,
      });
    }
    for (const label of candidates) {
      const element = labels.get(label.id)!;
      label.width = element.offsetWidth;
      label.height = element.offsetHeight + (element.classList.contains('is-leading') ? 12 : 0);
    }
    const stage = labels.values().next().value?.parentElement?.parentElement;
    const bounds = districtLabelBounds(stage, size.width, size.height);
    let placed = near
      ? positionSceneLabels(candidates, bounds)
      : positionDistrictLabels(candidates, bounds);
    if (!near && placed.length < candidates.length) {
      for (const label of candidates) labels.get(label.id)!.classList.add('is-compact');
      for (const label of candidates) {
        const element = labels.get(label.id)!;
        label.width = element.offsetWidth;
        label.height = element.offsetHeight;
      }
      placed = positionDistrictLabels(candidates, bounds);
    }
    for (const label of candidates) labels.get(label.id)!.style.display = 'none';
    for (const label of placed) {
      const element = labels.get(label.id);
      if (!element) continue;
      element.style.display = 'block';
      element.style.transform = `translate(${label.x}px,${label.y}px) translate(-50%,-50%)`;
      const anchor = candidates.find((v) => v.id === label.id)!;
      const end = labelLeaderEnd(anchor, label);
      const dx = anchor.x - end.x,
        dy = anchor.y - end.y;
      element.style.setProperty('--leader-left', `${end.x - label.x + label.width / 2}px`);
      element.style.setProperty('--leader-top', `${end.y - label.y + label.height / 2}px`);
      element.style.setProperty('--leader-width', `${near ? 0 : Math.hypot(dx, dy)}px`);
      element.style.setProperty('--leader-angle', `${Math.atan2(dy, dx)}rad`);
    }
  });
  return null;
}
const CityScene = memo(function CityScene({
  audio,
  urbanClock,
  streets,
  railTraffic,
  railServices,
  topography,
  parking,
  population,
  livePlaces,
  historical,
  onFloodStats,
  waterWeather = calmWater,
  surfaceFrame = null,
  publicSurfaceFrames = [],
  surfaceMetric = 'depth',
  onSurfaceError,
  traceTiles,
  onTraceError,
  publicAssets,
  selectedAssetId,
  onAsset,
  terrain,
  city,
  regions,
  tiles,
  focus,
  selected,
  onCamera,
  onNavigate,
  labels,
  onUnavailable,
  ownDistrictId,
  sites,
  groundCandidates,
  showCandidates = false,
  occupiedSites,
  installations,
  installationBySite,
  selectedSite,
  onSite,
  wetDistricts,
  rainAmounts,
  rainCamera,
  animateRain,
  preview,
  onBuilding,
  onStreet,
  onParking,
  eligibleRoofs,
  occupiedRoofs,
  facilityType,
  viewerId,
  planningRoles,
  cisternGeometry,
  watershed,
}: {
  watershed?: WatershedMapSelection | null;
  audio: AudioHandle;
  urbanClock: UrbanTime;
  streets: Street[];
  railTraffic: Street[];
  railServices?: import('../../urban/service/railLifeService').RailService[];
  topography: TopographyView;
  parking: ParkingData | null;
  population: Population | null;
  livePlaces: LivePlace[];
  historical: boolean;
  onFloodStats: (stats: FloodStats) => void;
  cisternGeometry?: CisternMapPreview | null;
  planningRoles?: ReadonlyMap<string, CisternSiteRole>;
  surfaceFrame?: SurfaceFrame | null;
  publicSurfaceFrames?: PublicFrame[];
  surfaceMetric?: SurfaceMetric;
  onSurfaceError: () => void;
  traceTiles: TraceTile[];
  onTraceError: () => void;
  publicAssets: InfrastructureAsset[];
  selectedAssetId: string;
  onAsset: (asset: InfrastructureAsset) => void;
  terrain: Terrain | null;
  city: City;
  regions: CityPlayRegion[];
  tiles: CityTile[];
  focus: CityFocus;
  selected: string;
  onCamera: (state: CameraState) => void;
  onNavigate: (state: CameraState) => void;
  labels: Map<string, HTMLElement>;
  onUnavailable: () => void;
  ownDistrictId: string | null;
  groundCandidates: GroundCandidate[];
  showCandidates?: boolean;
  occupiedSites: ReadonlySet<string>;
  sites: SharedSite[];
  installations: SharedInstallation[];
  installationBySite: ReadonlyMap<string, InstallationLayout>;
  selectedSite: string;
  onSite: (key: string) => void;
  wetDistricts: City['districts'];
  rainAmounts: ReadonlyMap<string, number | null>;
  rainCamera: CameraState;
  animateRain: boolean;
  waterWeather?: WaterWeather;
  preview: { site: SharedSite; placement: Placement } | null;
  onBuilding: (districtId: string, b: CityBuilding) => void;
  onStreet?: (sourceId: string, point: [number, number]) => void;
  onParking?: (sourceId: string, point: [number, number]) => void;
  eligibleRoofs: ReadonlySet<string>;
  occupiedRoofs: ReadonlySet<string>;
  facilityType: FacilityType | '';
  viewerId: string | null;
}) {
  const parkingLots = useParkingLots(
    parking,
    rainCamera.center,
    rainCamera.distance,
    sites,
    installationBySite
  );
  const connected = useServerConnected();
  const reactions = useRef({ traffic: emptyFloodStats, parking: emptyFloodStats });
  const reporters = useMemo(
    () =>
      Object.fromEntries(
        ['traffic', 'parking'].map((kind) => [
          kind,
          (stats: FloodStats) => {
            reactions.current[kind as 'traffic' | 'parking'] = stats;
            const { traffic, parking } = reactions.current;
            onFloodStats({
              stopped: traffic.stopped + parking.stopped,
              exposed: traffic.exposed + parking.exposed,
              avoiding: traffic.avoiding + parking.avoiding,
              stranded: traffic.stranded + parking.stranded,
            });
          },
        ])
      ) as Record<'traffic' | 'parking', (stats: FloodStats) => void>,
    [onFloodStats]
  );
  const flood = createFloodField(
    surfaceFrame ? [surfaceFrame] : publicSurfaceFrames.map((value) => value.frame),
    traceTiles,
    historical
  );
  const publicBuildings = useMemo(
    () => publicInfrastructureBuildingIds(publicAssets),
    [publicAssets]
  );
  const [overviewActive, setOverviewActive] = useState(focus.overview === true);
  const overviewIds = useMemo(() => new Set(city.overviewBuildings.map((b) => b.id)), [city]);
  const detailTileIds = useMemo(() => new Set(tiles.map((tile) => tile.id)), [tiles]);
  const symbols = useMemo(
    () => installationSymbols(installations, viewerId),
    [installations, viewerId]
  );
  return (
    <Canvas
      onPointerMoveCapture={(event) => {
        if (event.target instanceof HTMLCanvasElement)
          event.target.style.cursor = event.buttons ? 'grabbing' : 'grab';
      }}
      shadows
      events={mapEvents}
      frameloop={connected ? 'demand' : 'never'}
      dpr={[1, 1.5]}
      camera={{ position: [0, 30000, 22000], near: 5, far: 600000, fov: 45 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
    >
      <TerrainContext.Provider value={terrain}>
        <CityAudioListener audio={audio} />
        <UrbanEnvironment clock={urbanClock}>
          <WaterScene animate={animateRain} clock={urbanClock}>
            <InfrastructureFootprints
              assets={publicAssets}
              selectedId={selectedAssetId}
              terrain={terrain}
              onSelect={onAsset}
            />
            <FloodTraceLayer
              tiles={traceTiles}
              terrain={terrain}
              onError={onTraceError}
              weather={waterWeather}
            />
            <SurfaceLayer
              frame={surfaceFrame}
              metric={surfaceMetric}
              terrain={terrain}
              onError={onSurfaceError}
              weather={waterWeather}
            />
            {!surfaceFrame &&
              publicSurfaceFrames.map((value) => (
                <SurfaceLayer
                  key={value.id}
                  frame={value.frame}
                  metric={surfaceMetric}
                  terrain={terrain}
                  onError={onSurfaceError}
                  weather={waterWeather}
                />
              ))}
            <InfrastructureMarkers
              distance={rainCamera.distance}
              assets={publicAssets}
              selectedId={selectedAssetId}
              terrain={terrain}
              onSelect={onAsset}
            />
            {terrain ? (
              <TerrainSurface
                districtIds={city.districts.map((d) => d.id)}
                terrain={terrain}
                ownDistrictId={ownDistrictId}
                selected={selected}
              />
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
            <CityOverview
              districtIds={city.districts.map((d) => d.id)}
              center={rainCamera.center}
              distance={rainCamera.distance}
              terrain={terrain}
              detailTileIds={detailTileIds}
              ownDistrictId={ownDistrictId}
            />
            <StreetLayer
              roads={streets}
              center={rainCamera.center}
              parking={parking}
              terrain={terrain}
              detail={rainCamera.distance < 4500}
              onStreet={onStreet}
            />
            <TopographyLayer value={topography} distance={rainCamera.distance} />
            <TopographyLabels value={topography} terrain={terrain} distance={rainCamera.distance} />
            <StreetLife
              audio={audio}
              roads={streets}
              parking={parking}
              terrain={terrain}
              center={rainCamera.center}
              distance={rainCamera.distance}
              clock={urbanClock}
              population={population}
              livePlaces={livePlaces}
              flood={flood}
              onFloodStats={reporters.traffic}
              city={city}
              animate={animateRain}
            />
            <RailLife
              roads={railTraffic}
              preparedServices={railServices}
              terrain={terrain}
              center={rainCamera.center}
              distance={rainCamera.distance}
              clock={urbanClock}
              animate={animateRain}
            />
            <ParkingLayer
              lots={parkingLots}
              terrain={terrain}
              center={rainCamera.center}
              flood={flood}
              clock={urbanClock}
              animate={animateRain}
              onFloodStats={reporters.parking}
              onParking={onParking}
            />
            <GroundCandidates
              rows={groundCandidates}
              showColors={showCandidates}
              occupiedSites={occupiedSites}
              terrain={terrain}
              type={facilityType}
              ownDistrictId={ownDistrictId}
              onSelect={onSite}
            />
            <RiverLayer city={city} terrain={terrain} weather={waterWeather} />
            {!terrain &&
              city.surfaces
                .filter((s) => s.kind !== 'water')
                .map((s, i) => (
                  <Surface
                    key={i}
                    polygons={s.polygons}
                    color={s.kind === 'water' ? '#81b1ba' : '#b4c8a3'}
                    height={s.kind === 'water' ? 4 : 2}
                  />
                ))}
            <DistrictBuildings
              publicBuildings={publicBuildings}
              facilityType={facilityType}
              eligibleRoofs={eligibleRoofs}
              showCandidates={showCandidates}
              occupiedRoofs={occupiedRoofs}
              buildings={city.overviewBuildings}
              ownDistrictId={ownDistrictId}
              onBuilding={onBuilding}
            />
            {tiles.map((t) => (
              <DetailBuildings
                publicBuildings={publicBuildings}
                exclude={overviewIds}
                facilityType={facilityType}
                key={t.id}
                eligibleRoofs={eligibleRoofs}
                showCandidates={showCandidates}
                occupiedRoofs={occupiedRoofs}
                buildings={t.buildings}
                onBuilding={onBuilding}
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
                          if (index % 3 === 0)
                            out.push([value, values[index + 1], values[index + 2]]);
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
                  (site.districtId === selected && site.cellId === selectedSite) ||
                  installationBySite.has(siteKey(site)) ||
                  planningRoles?.has(siteKey(site))
              )
              .map((site) => {
                const installed = installationBySite.get(siteKey(site));
                const selectedSiteHere =
                  site.districtId === selected && site.cellId === selectedSite;
                const appearance = siteAppearance({
                  eligible:
                    !site.existingInfrastructure && (!installed || installed.ownerId !== viewerId),
                  matches: !facilityType || site.allowedTypes.includes(facilityType),
                  selected: selectedSiteHere,
                  installed: !!installed,
                  otherDistrict: !!ownDistrictId && site.districtId !== ownDistrictId,
                });
                return (
                  <group key={siteKey(site)}>
                    <SiteSurface
                      site={site}
                      installed={!!installed || !!site.existingInfrastructure}
                      color={
                        planningRoles?.has(siteKey(site)) && !selectedSiteHere
                          ? cisternSiteColors[planningRoles.get(siteKey(site))!]
                          : appearance.color
                      }
                      selected={selectedSiteHere}
                      opacity={appearance.opacity}
                      onClick={() => onSite(siteKey(site))}
                    />
                    {installed && (
                      <FacilityMesh
                        terrain={terrain}
                        cell={{
                          ...site,
                          heightM:
                            (site.kind === 'ROOF'
                              ? buildingBaseElevation(terrain, site.polygons)
                              : terrainHeight(terrain, site.center)) +
                            (site.kind === 'ROOF' ? site.heightM : 0.2),
                        }}
                        placement={installed}
                        preview={false}
                        opacity={buildingOpacity(
                          !facilityType || installed.facilityType === facilityType,
                          !!ownDistrictId && site.districtId !== ownDistrictId
                        )}
                        onSelect={() => onSite(siteKey(site))}
                      />
                    )}
                  </group>
                );
              })}
            {cisternGeometry && <CisternLayoutMesh geometry={cisternGeometry} terrain={terrain} />}
            {watershed && <WatershedMapMesh {...watershed} terrain={terrain} />}
            {preview && (
              <FacilityMesh
                terrain={terrain}
                cell={{
                  ...preview.site,
                  heightM:
                    (preview.site.kind === 'ROOF'
                      ? buildingBaseElevation(terrain, preview.site.polygons)
                      : terrainHeight(terrain, preview.site.center)) +
                    (preview.site.kind === 'ROOF' ? preview.site.heightM : 0.2),
                }}
                placement={preview.placement}
                preview
                opacity={buildingOpacity(
                  true,
                  !!ownDistrictId && preview.site.districtId !== ownDistrictId
                )}
                onSelect={() => onSite(siteKey(preview.site))}
              />
            )}
            <InstallationSymbols
              installations={symbols}
              viewerId={viewerId}
              facilityType={facilityType}
              selectedKey={`${selected}:${selectedSite}`}
              ownDistrictId={ownDistrictId}
              terrain={terrain}
              onSelect={onSite}
            />
            <LiveRainScene
              timeline={urbanClock}
              externalClock
              districts={wetDistricts}
              amounts={rainAmounts}
              center={rainCamera.center}
              distance={rainCamera.distance}
              animate={animateRain}
              terrain={terrain}
            />
            <ProjectedLabels
              city={city}
              regions={regions}
              labels={labels}
              selected={selected}
              overview={overviewActive}
            />
            {!facilityType && (
              <InstallationNameplates
                center={rainCamera.center}
                installations={installations}
                terrain={terrain}
                selectedKey={`${selected}:${selectedSite}`}
                viewerId={viewerId}
                distance={rainCamera.distance}
                onSelect={onSite}
              />
            )}
            <Controls
              focus={focus}
              bounds={city.bounds}
              onCamera={onCamera}
              onNavigate={onNavigate}
              onUnavailable={onUnavailable}
              onOverview={setOverviewActive}
            />
          </WaterScene>
        </UrbanEnvironment>
      </TerrainContext.Provider>
    </Canvas>
  );
});
export default CityScene;

function SiteSurface({
  site,
  installed,
  color,
  opacity,
  selected,
  onClick,
}: {
  site: SharedSite;
  installed: boolean;
  color: string;
  opacity: number;
  selected: boolean;
  onClick: () => void;
}) {
  const terrain = useContext(TerrainContext);
  const geometry = useMemo(
    () =>
      pavementGeometry(
        placementFootprint(site, {
          cellId: site.cellId,
          facilityType: 'PERMEABLE_PAVEMENT',
          areaM2: site.maxAreaM2,
        }),
        site.kind === 'GROUND' ? terrain : null,
        site.kind === 'GROUND'
          ? candidateSurfaceLift
          : buildingBaseElevation(terrain, site.polygons) + site.heightM + 0.11
      ),
    [site, terrain]
  );
  const outlinePoints = useMemo(() => {
    const data = geometry.outline.getAttribute('position');
    return Array.from({ length: data.count }, (_, i): [number, number, number] => [
      data.getX(i),
      data.getY(i),
      data.getZ(i),
    ]);
  }, [geometry]);
  useEffect(() => () => Object.values(geometry).forEach((value) => value.dispose()), [geometry]);
  return (
    <group>
      <mesh
        onPointerMove={(event) => scenePointer(event, installed ? 'inspect' : 'install')}
        onPointerOut={clearScenePointer}
        geometry={geometry.surface}
        renderOrder={selected ? 75 : 2}
        onClick={(event) => {
          if (event.delta > 5) return;
          event.stopPropagation();
          onClick();
        }}
      >
        <meshBasicMaterial
          color={color}
          side={THREE.DoubleSide}
          transparent
          opacity={opacity * (selected ? 0.24 : 0.42)}
          depthTest={!selected}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
      {selected ? (
        <Line
          points={outlinePoints}
          segments
          color={color}
          lineWidth={2.5}
          transparent
          toneMapped={false}
          depthTest={false}
          depthWrite={false}
          renderOrder={76}
          raycast={() => {}}
        />
      ) : (
        <lineSegments geometry={geometry.outline} renderOrder={3} raycast={() => {}}>
          <lineBasicMaterial
            color={color}
            transparent
            opacity={opacity * 0.8}
            depthWrite={false}
            toneMapped={false}
          />
        </lineSegments>
      )}
    </group>
  );
}
function DistrictBuildings({
  buildings,
  publicBuildings,
  ownDistrictId,
  onBuilding,
  eligibleRoofs,
  occupiedRoofs,
  facilityType,
  showCandidates = false,
}: {
  showCandidates?: boolean;
  buildings: CityBuilding[];
  publicBuildings: ReadonlySet<string>;
  ownDistrictId: string | null;
  onBuilding: (districtId: string, b: CityBuilding) => void;
  eligibleRoofs: ReadonlySet<string>;
  occupiedRoofs: ReadonlySet<string>;
  facilityType: FacilityType | '';
}) {
  function selectBuilding(b: CityBuilding) {
    onBuilding(b.districtId, b);
  }
  const groups = useMemo(() => {
    const buckets = new Map<
      string,
      { eligible: boolean; other: boolean; buildings: CityBuilding[] }
    >();
    for (const b of buildings) {
      if (publicBuildings.has(b.id)) continue;
      const other = !!ownDistrictId && b.districtId !== ownDistrictId;
      const eligible = eligibleRoofs.has(b.id) && !occupiedRoofs.has(b.id);
      const key = `${eligible}:${other}`;
      if (!buckets.has(key)) buckets.set(key, { eligible, other, buildings: [] });
      buckets.get(key)!.buildings.push(b);
    }
    return [...buckets.entries()];
  }, [buildings, publicBuildings, ownDistrictId, eligibleRoofs, occupiedRoofs]);
  return (
    <>
      {groups.map(([key, values]) => (
        <Buildings
          key={key}
          buildings={values.buildings}
          available={
            showCandidates &&
            values.eligible &&
            (!facilityType || facilityType === 'GREEN_ROOF' || facilityType === 'RAINWATER_CISTERN')
          }
          opacity={
            showCandidates
              ? buildingOpacity(
                  showCandidates &&
                    values.eligible &&
                    (!facilityType ||
                      facilityType === 'GREEN_ROOF' ||
                      facilityType === 'RAINWATER_CISTERN'),
                  values.other
                )
              : values.other
                ? otherDistrictOpacity
                : 1
          }
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
