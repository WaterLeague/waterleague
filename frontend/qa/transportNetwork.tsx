import { createFloodField } from '../src/domains/urban/service/floodFieldService';
import { StreetLife } from '../src/domains/urban/view/StreetLife';
import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas, useThree } from '@react-three/fiber';
import { Mesh, Raycaster, Vector2 } from 'three';
import { OrbitControls } from '@react-three/drei';
import { loadCity } from '../src/domains/city/repository/cityRepository';
import { useCityTiles } from '../src/domains/city/controller/useCity';
import { useUrbanData } from '../src/domains/urban/controller/useUrbanData';
import { useTopography } from '../src/domains/topography/controller/useTopography';
import { loadTerrain } from '../src/domains/terrain/repository/terrainRepository';
import { TerrainSurface } from '../src/domains/terrain/view/TerrainSurface';
import { RiverLayer } from '../src/domains/surface/view/RiverLayer';
import { WaterScene } from '../src/domains/surface/view/WaterScene';
import { calmWater } from '../src/domains/surface/service/waterAppearanceService';
import { StreetLayer } from '../src/domains/urban/view/StreetLayer';
import { RailLife } from '../src/domains/urban/view/RailLife';
import { TopographyLayer } from '../src/domains/topography/view/TopographyLayer';
import { terrainMeshHeight } from '../src/domains/terrain/service/terrainDrapeService';
import type { City } from '../src/domains/city/entity/city';
import type { Terrain } from '../src/domains/terrain/entity/terrain';
import type { UrbanTime } from '../src/domains/urban/entity/urban';
if (!import.meta.env.DEV || !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
  throw new Error('로컬 검증 전용');
const places = [
  { name: '양화대교 남단 하부 횡단부', center: [-7035, -3320] as [number, number], distance: 65 },
  { name: '양화대교 남단 진입부', center: [-6990, -3240] as [number, number], distance: 160 },
  { name: '양화대교 북단 진입부', center: [-6140, -2330] as [number, number], distance: 210 },
  {
    name: '강남대로·한남대교 접속부',
    center: [2874.296, -4283.443] as [number, number],
    distance: 180,
  },
  {
    name: '강남대로 강남역 교차로',
    center: [4314.38, -7713.15] as [number, number],
    distance: 240,
  },
  { name: '남산3호터널 입구', center: [840, -2510] as [number, number], distance: 180 },
  { name: '가양대교 남단·수면', center: [-10630, -220] as [number, number], distance: 420 },
  { name: '성산대교 남단·수면', center: [-7880, -2050] as [number, number], distance: 420 },
  { name: '노들섬 연결 전체', center: [-1760, -5550] as [number, number], distance: 650 },
  { name: '한강철교 열차', center: [-2340, -5300] as [number, number], distance: 230 },
  { name: '잠수교 하층', center: [1570, -5860] as [number, number], distance: 240 },
  { name: '청담대교 하층 전철', center: [7530, -4650] as [number, number], distance: 180 },
  { name: '도심 도로 차선', center: [-1590, -4920] as [number, number], distance: 250 },
  { name: '가양대교 육지 접속부', center: [-10820, -540] as [number, number], distance: 220 },
  { name: '노들섬 중앙 연결부', center: [-1760, -5530] as [number, number], distance: 280 },
  { name: '선유도·양화대교 통과부', center: [-6630, -2750] as [number, number], distance: 400 },
  { name: '밤섬·서강대교 통과부', center: [-4790, -3580] as [number, number], distance: 400 },
];
function GeometryProbe({ onPoint }: { onPoint: (text: string) => void }) {
  const { gl, camera, scene } = useThree();
  useEffect(() => {
    const pick = (event: PointerEvent) => {
      if (event.button !== 0) return;
      const rect = gl.domElement.getBoundingClientRect(),
        ray = new Raycaster();
      ray.setFromCamera(
        new Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          (-(event.clientY - rect.top) / rect.height) * 2 + 1
        ),
        camera
      );
      const hits: { point: { x: number; y: number; z: number }; distance: number }[] = [];
      scene.traverse((node) => {
        if (
          !(node instanceof Mesh) ||
          'isInstancedMesh' in node ||
          !node.visible ||
          Array.isArray(node.material) ||
          !node.material.colorWrite
        )
          return;
        const mesh = new Mesh(node.geometry, node.material);
        mesh.matrixWorld.copy(node.matrixWorld);
        mesh.raycast(ray, hits as never);
      });
      hits.sort((a, b) => a.distance - b.distance);
      if (hits[0]) {
        const p = hits[0].point;
        onPoint(`표시 면 @ ${p.x.toFixed(3)}, ${(-p.z).toFixed(3)} · 높이 ${p.y.toFixed(3)}`);
      }
    };
    gl.domElement.addEventListener('pointerup', pick);
    return () => gl.domElement.removeEventListener('pointerup', pick);
  }, [gl, camera, scene, onPoint]);
  return null;
}
function Map({ city, terrain }: { city: City; terrain: Terrain }) {
  const [probe, setProbe] = useState('');
  const [selected, setSelected] = useState(0),
    [playing, setPlaying] = useState(true);
  const camera = places[selected],
    center = camera.center,
    distance = camera.distance;
  const { tiles, error: tileError, busy } = useCityTiles(city, camera);
  const { roads, railTraffic, railServices, error } = useUrbanData(tiles, center, distance);
  const topography = useTopography(center, distance, terrain, false);
  const clock = useRef({
    historical: false,
    at: null,
    playing: true,
    speed: 1,
    sampledAt: performance.now(),
  }) as UrbanTime;
  const ground = terrainMeshHeight(terrain, center);
  return (
    <main style={{ height: '100vh', fontFamily: 'system-ui' }}>
      <header
        style={{
          position: 'absolute',
          zIndex: 2,
          top: 12,
          left: 12,
          padding: 12,
          background: '#fffffff0',
          borderRadius: 8,
        }}
      >
        <b>실제 지도 교통 연결 검증</b>
        <br />
        <select
          aria-label="검증 위치"
          value={selected}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {places.map((p, i) => (
            <option key={p.name} value={i}>
              {p.name}
            </option>
          ))}
        </select>
        <button onClick={() => setPlaying(!playing)}>
          {playing ? '이동체 일시정지' : '이동체 재생'}
        </button>
        <p style={{ marginBottom: 0, fontSize: 12 }}>
          원본 선형 · 높이·차선 간격·열차 운행은 표시 가정
        </p>
        <output>
          {error ||
            tileError ||
            topography.error ||
            `${busy || topography.busy ? '불러오는 중' : '준비 완료'} · 도로 ${roads.length} · 철도 ${roads.filter((r) => r.nativeRailKind).length} · 원 타일 ${topography.tiles.length}`}
        </output>
        {probe && (
          <output style={{ display: 'block', maxWidth: 420, overflowWrap: 'anywhere' }}>
            {probe}
          </output>
        )}
      </header>
      <Canvas
        key={selected}
        camera={{
          position: [
            center[0] + distance * 0.3,
            ground + distance * 0.5,
            -center[1] + distance * 0.85,
          ],
          near: 0.2,
          far: 50000,
        }}
        dpr={[1, 1.5]}
      >
        <color attach="background" args={['#d8e1df']} />
        <hemisphereLight args={['#fffbe9', '#7e8f81', 2.2]} />
        <directionalLight position={[100, 500, 200]} intensity={2} />
        <GeometryProbe onPoint={setProbe} />
        <WaterScene animate={playing} clock={clock}>
          <TerrainSurface terrain={terrain} ownDistrictId={null} selected="" />
          <StreetLayer
            roads={roads}
            terrain={terrain}
            detail
            center={center}
            onStreet={() => undefined}
          />
          <TopographyLayer value={topography} distance={distance} />
          <RiverLayer city={city} terrain={terrain} weather={calmWater} />
          <StreetLife
            roads={roads}
            terrain={terrain}
            center={center}
            distance={distance}
            clock={clock}
            population={null}
            livePlaces={[]}
            flood={createFloodField([], [], false)}
            city={city}
            animate={playing}
          />
          <RailLife
            roads={railTraffic}
            preparedServices={railServices}
            terrain={terrain}
            center={center}
            distance={distance}
            clock={clock}
            animate={playing}
          />
        </WaterScene>
        <OrbitControls
          target={[center[0], ground + 10, -center[1]]}
          minDistance={10}
          maxDistance={5000}
        />
      </Canvas>
    </main>
  );
}
function App() {
  const [data, setData] = useState<{ city: City; terrain: Terrain } | null>(null);
  useEffect(() => {
    const c = new AbortController();
    void Promise.all([loadCity(c.signal), loadTerrain(c.signal)]).then(([city, terrain]) => {
      if (!c.signal.aborted) setData({ city, terrain });
    });
    return () => c.abort();
  }, []);
  return data ? <Map {...data} /> : <p>원본 지도 불러오는 중</p>;
}
const root = createRoot(document.getElementById('root')!);
root.render(<App />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());
