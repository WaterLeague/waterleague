import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas } from '@react-three/fiber';
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
  { name: '가양대교 남단·수면', center: [-10630, -220] as [number, number], distance: 420 },
  { name: '성산대교 남단·수면', center: [-7880, -2050] as [number, number], distance: 420 },
  { name: '노들섬 연결 전체', center: [-1760, -5550] as [number, number], distance: 650 },
  { name: '한강철교 열차', center: [-2340, -5300] as [number, number], distance: 230 },
  { name: '잠수교 하층', center: [1570, -5860] as [number, number], distance: 240 },
  { name: '청담대교 하층 전철', center: [7530, -4650] as [number, number], distance: 180 },
  { name: '도심 도로 차선', center: [-1590, -4920] as [number, number], distance: 250 },
];
function Map({ city, terrain }: { city: City; terrain: Terrain }) {
  const [selected, setSelected] = useState(0),
    [playing, setPlaying] = useState(true);
  const camera = places[selected],
    center = camera.center,
    distance = camera.distance;
  const { tiles, error: tileError, busy } = useCityTiles(city, camera);
  const { roads, error } = useUrbanData(tiles, center, distance);
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
          {playing ? '열차 일시정지' : '열차 재생'}
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
        <WaterScene animate={playing} clock={clock}>
          <TerrainSurface terrain={terrain} ownDistrictId={null} selected="" />
          <StreetLayer roads={roads} terrain={terrain} detail center={center} />
          <TopographyLayer value={topography} distance={distance} />
          <RiverLayer city={city} terrain={terrain} weather={calmWater} />
          <RailLife
            roads={roads}
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
createRoot(document.getElementById('root')!).render(<App />);
