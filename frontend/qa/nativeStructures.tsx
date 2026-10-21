import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { BufferAttribute, BufferGeometry, DoubleSide } from 'three';
import { loadNativeBridges } from '../src/domains/urban/repository/nativeBridgeRepository';
import { loadTerrain } from '../src/domains/terrain/repository/terrainRepository';
import { nativeStreets } from '../src/domains/urban/service/nativeStreetService';
import { streetGeometry } from '../src/domains/urban/service/streetGeometryService';
import { nativeBridgeHeight } from '../src/domains/urban/service/nativeBridgeService';
import { terrainMeshHeight } from '../src/domains/terrain/service/terrainDrapeService';
import {
  loadTopographyIndex,
  requestTopographyTile,
} from '../src/domains/topography/repository/topographyRepository';
import { TopographyLayer } from '../src/domains/topography/view/TopographyLayer';
import type { TopographyBuffers } from '../src/domains/topography/entity/topography';
import type { NativeBridgeGroup } from '../src/domains/urban/dto/nativeBridgeDto';
import { loadCity } from '../src/domains/city/repository/cityRepository';
import { riverGeometry } from '../src/domains/surface/service/riverGeometry';
import type { City } from '../src/domains/city/entity/city';
import type { Terrain } from '../src/domains/terrain/entity/terrain';
if (!import.meta.env.DEV || !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
  throw new Error('로컬 개발 검증 전용');
function geometry(positions: Float32Array, colors?: Float32Array) {
  const value = new BufferGeometry();
  value.setAttribute('position', new BufferAttribute(positions, 3));
  if (colors) value.setAttribute('color', new BufferAttribute(colors, 3));
  value.computeVertexNormals();
  return value;
}
function Scene({
  group,
  terrain,
  focus,
  features,
  city,
  lowerOnly,
}: {
  group: NativeBridgeGroup;
  terrain: Terrain;
  focus: 'bridge' | 'objects';
  features: TopographyBuffers | null;
  city: City;
  lowerOnly: boolean;
}) {
  const center = useMemo(() => {
    if (focus === 'objects' && features) {
      const m = features.models.find((m) => m.kind === 'TREE') ?? features.models[0];
      if (m) return [m.matrices[12], -m.matrices[14]] as [number, number];
    }
    const p = group.profiles.find((p) => !p.steps) ?? group.profiles[0];
    if (p) {
      let walked = 0;
      const target = group.lowerDeck ? (p.span[0] + p.span[1]) / 2 : p.span[0];
      for (let i = 1; i < p.coordinates.length; i++) {
        const a = p.coordinates[i - 1],
          b = p.coordinates[i],
          d = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (walked + d >= target) {
          const t = (target - walked) / d;
          return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t] as [number, number];
        }
        walked += d;
      }
    }
    return [(group.bounds[0] + group.bounds[2]) / 2, (group.bounds[1] + group.bounds[3]) / 2] as [
      number,
      number,
    ];
  }, [group, focus, features]);
  const ground = terrainMeshHeight(terrain, center),
    span = focus === 'bridge' ? (group.lowerDeck ? 95 : 180) : 55;
  const meshes = useMemo(() => {
    const streets = nativeStreets([], [group]);
    const bridge = streetGeometry(
        lowerOnly ? streets.filter((s) => s.nativeDeckLevel !== 'upper') : streets,
        terrain,
        true
      ),
      positions: number[] = [];
    for (let x = center[0] - 400; x < center[0] + 400; x += 10)
      for (let y = center[1] - 400; y < center[1] + 400; y += 10)
        for (const p of [
          [x, y],
          [x + 10, y],
          [x, y + 10],
          [x, y + 10],
          [x + 10, y],
          [x + 10, y + 10],
        ] as [number, number][])
          positions.push(p[0], terrainMeshHeight(terrain, p), -p[1]);
    return {
      bridge: geometry(bridge.positions, bridge.colors),
      ground: geometry(new Float32Array(positions)),
    };
  }, [group, terrain, center, lowerOnly]);
  const water = useMemo(() => {
    const data = riverGeometry(
      city.surfaces.filter((s) => s.kind === 'water').map((s) => s.polygons),
      terrain
    );
    return geometry(data.positions);
  }, [city, terrain]);
  useEffect(() => () => water.dispose(), [water]);
  useEffect(() => () => Object.values(meshes).forEach((m) => m.dispose()), [meshes]);
  return (
    <Canvas
      key={center.join(',') + focus}
      camera={{
        position: [
          center[0] + span * 0.65,
          (focus === 'bridge'
            ? nativeBridgeHeight(terrain, group.displayDatumPolygons ?? group.polygons)
            : ground) +
            span * 0.3,
          -center[1] + span * 0.8,
        ],
        near: 0.2,
        far: 50000,
      }}
      dpr={[1, 1.5]}
    >
      <color attach="background" args={['#d8e1df']} />
      <hemisphereLight args={['#fffbe9', '#7e8f81', 2.2]} />
      <directionalLight position={[100, 500, 200]} intensity={2} />
      <mesh geometry={meshes.ground}>
        <meshStandardMaterial color="#c5ceb8" side={DoubleSide} />
      </mesh>
      <mesh geometry={water}>
        <meshStandardMaterial color="#287b91" side={DoubleSide} roughness={0.35} />
      </mesh>
      <mesh geometry={meshes.bridge}>
        <meshStandardMaterial vertexColors side={DoubleSide} roughness={0.9} />
      </mesh>
      {features && focus === 'objects' && (
        <TopographyLayer
          value={{ index: null, tiles: [{ id: 'source', data: features }] }}
          distance={55}
        />
      )}
      <OrbitControls
        target={[
          center[0],
          focus === 'bridge'
            ? nativeBridgeHeight(terrain, group.displayDatumPolygons ?? group.polygons)
            : ground,
          -center[1],
        ]}
        minDistance={5}
        maxDistance={5000}
      />
    </Canvas>
  );
}
function App() {
  const [data, setData] = useState<{
      groups: NativeBridgeGroup[];
      terrain: Terrain;
      city: City;
    } | null>(null),
    [features, setFeatures] = useState<TopographyBuffers | null>(null),
    [selected, setSelected] = useState(0),
    [focus, setFocus] = useState<'bridge' | 'objects'>('bridge'),
    [error, setError] = useState(''),
    [lowerOnly, setLowerOnly] = useState(false);
  useEffect(() => {
    const request = new AbortController();
    void Promise.all([
      loadNativeBridges(request.signal),
      loadTerrain(request.signal),
      loadCity(request.signal),
    ])
      .then(([groups, terrain, city]) => {
        groups.sort(
          (a, b) =>
            Number(!!b.lowerDeck) - Number(!!a.lowerDeck) || b.sourceIds.length - a.sourceIds.length
        );
        setData({ groups, terrain, city });
        return loadTopographyIndex(request.signal).then((index) => {
          const tile = index.tiles.find((t) => t.id === '-1_-8')!;
          return requestTopographyTile(tile, index.layers, terrain, false, request.signal).then(
            setFeatures
          );
        });
      })
      .catch(() => setError('원본 구조 검증 자료 로드 실패'));
    return () => request.abort();
  }, []);
  return (
    <main style={{ height: '100vh', fontFamily: 'system-ui' }}>
      <header
        style={{
          position: 'absolute',
          zIndex: 2,
          top: 12,
          left: 12,
          background: '#fffffff0',
          padding: 12,
          borderRadius: 8,
          maxWidth: 430,
        }}
      >
        <strong>원본 3D 구조 검증 · 제품 빌드 제외</strong>
        <div>
          <button onClick={() => setFocus('bridge')}>교량 접속부</button>
          <button onClick={() => setFocus('objects')}>도심 입체 지물</button>
        </div>
        <label>
          <input
            type="checkbox"
            checked={lowerOnly}
            onChange={(e) => setLowerOnly(e.target.checked)}
          />
          하층만 보기
        </label>
        {data && (
          <select
            aria-label="원본 교량 선택"
            value={selected}
            onChange={(e) => setSelected(Number(e.target.value))}
          >
            {data.groups.map((g, i) => (
              <option key={g.id} value={i}>
                {g.names?.join(' · ') || `구조 ${i + 1}`} · 원본 {g.sourceIds.length}조각 · 접속{' '}
                {g.profiles.length}개
              </option>
            ))}
          </select>
        )}
        <p style={{ fontSize: 12, marginBottom: 0 }}>
          원본 위치·외곽 유지. 모형 제원·교량 표시 높이는 시각화 가정.
        </p>
        <output>
          {error ||
            (!data
              ? '원본 불러오는 중'
              : `준비 완료 · ${data.groups.length}개 구조${features ? ' · 입체 지물 준비' : ''}`)}
        </output>
      </header>
      {data && (
        <Scene
          group={data.groups[selected]}
          terrain={data.terrain}
          focus={focus}
          features={features}
          city={data.city}
          lowerOnly={lowerOnly}
        />
      )}
    </main>
  );
}
createRoot(document.getElementById('root')!).render(<App />);
