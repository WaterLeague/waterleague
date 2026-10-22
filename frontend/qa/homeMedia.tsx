import { useCallback, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CityScene from '../src/domains/city/view/CityScene';
import { useCity, useCityTiles } from '../src/domains/city/controller/useCity';
import type { City, CityFocus } from '../src/domains/city/entity/city';
import { useTerrain } from '../src/domains/terrain/controller/useTerrain';
import { useUrbanData } from '../src/domains/urban/controller/useUrbanData';
import { useUrbanTime } from '../src/domains/urban/controller/useUrbanTime';
import { useTopography } from '../src/domains/topography/controller/useTopography';
import { useFloodTraces } from '../src/domains/floodtrace/controller/useFloodTraces';
import { createFloodField } from '../src/domains/urban/service/floodFieldService';

if (!import.meta.env.DEV || !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
  throw new Error('로컬 촬영 전용');

const noop = () => {};
const emptySet = new Set<string>();
const emptyMap = new Map();
const labels = new Map<string, HTMLElement>();
const floodMode = new URLSearchParams(location.search).has('flood');
if (floodMode) document.body.classList.add('flood-capture');

function Scene({ city }: { city: City }) {
  const [focus, setFocus] = useState<CityFocus>({
    center: [-1900, -5770],
    distance: 4200,
    key: 0,
  });
  const [camera, setCamera] = useState(focus);
  const [hour, setHour] = useState(14);
  const [failure, setFailure] = useState(false);
  const failed = useCallback(() => setFailure(true), []);
  const { terrain, error } = useTerrain();
  const details = useCityTiles(city, camera);
  const urban = useUrbanData(details.tiles, camera.center, camera.distance);
  const topography = useTopography(camera.center, camera.distance, terrain, false);
  const traces = useFloodTraces(floodMode, 'seoul-20220808', camera);
  const floodField = useMemo(() => createFloodField([], traces.tiles, true), [traces.tiles]);
  // 소개용 시각만 고정하고 게임의 원 지도·조명·생활인구 표시 경로를 그대로 사용한다.
  const at = `2026-10-22T${String(hour).padStart(2, '0')}:00:00+09:00`;
  const clock = useUrbanTime(true, at, false, 1, '2026-10-22T00:00:00+09:00');
  const streetClock = useUrbanTime(false, null, true, 1);
  const streetView = focus.distance < 250;
  const audio = useRef(null);
  const onCamera = useCallback((value: Omit<CityFocus, 'key'>) => {
    setCamera((old) =>
      JSON.stringify(old.center) === JSON.stringify(value.center) &&
      Math.abs(old.distance - value.distance) < 0.1
        ? old
        : { ...value, key: 0 }
    );
  }, []);
  const cameras = useMemo(
    () => ({
      river: { center: [-1900, -5770] as [number, number], distance: 4200 },
      street: { center: [6800, -3500] as [number, number], distance: 150 },
    }),
    []
  );
  const busy =
    details.busy || topography.busy || !terrain || !urban.population || !urban.roads.length;
  return (
    <>
      <header>
        {floodMode && (
          <button
            onClick={() => {
              let nearest = Infinity;
              let center: [number, number] | null = null;
              for (const road of urban.roads) {
                if (!road.motor || road.bridge || road.nativeBridgeProfiles?.length) continue;
                for (let i = 1; i < road.coordinates.length; i++)
                  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
                    const a = road.coordinates[i - 1],
                      b = road.coordinates[i];
                    const p: [number, number] = [
                      a[0] + (b[0] - a[0]) * t,
                      a[1] + (b[1] - a[1]) * t,
                    ];
                    const distance = Math.hypot(p[0] - camera.center[0], p[1] - camera.center[1]);
                    if (distance < nearest && floodField.contact(p)) {
                      nearest = distance;
                      center = p;
                    }
                  }
              }
              if (center) setFocus((v) => ({ center, distance: 130, key: v.key + 1 }));
            }}
          >
            침수 도로 확인
          </button>
        )}
        {floodMode && (
          <button
            onClick={() => {
              let nearest = Infinity;
              let center: [number, number] | null = null;
              for (const tile of traces.tiles)
                for (let i = 0; i < tile.triangleVertices.length; i += 6) {
                  const t = tile.triangleVertices;
                  const area = Math.abs(
                    (t[i + 2] - t[i]) * (t[i + 5] - t[i + 1]) -
                      (t[i + 4] - t[i]) * (t[i + 3] - t[i + 1])
                  );
                  if (area < 100) continue;
                  const p: [number, number] = [
                    (t[i] + t[i + 2] + t[i + 4]) / 3,
                    (t[i + 1] + t[i + 3] + t[i + 5]) / 3,
                  ];
                  const distance = Math.hypot(p[0] - camera.center[0], p[1] - camera.center[1]);
                  if (distance < nearest) {
                    nearest = distance;
                    center = p;
                  }
                }
              if (center) setFocus((v) => ({ center, distance: 220, key: v.key + 1 }));
            }}
          >
            침수 영역 가까이
          </button>
        )}
        {floodMode && (
          <button
            onClick={() => {
              const district = city.districts.find((d) => d.id === '11560');
              if (district)
                setFocus((v) => ({ center: district.center, distance: 900, key: v.key + 1 }));
            }}
          >
            영등포 침수 기록
          </button>
        )}
        <button onClick={() => setFocus((v) => ({ ...cameras.river, key: v.key + 1 }))}>
          한강 조망
        </button>
        <button onClick={() => setFocus((v) => ({ ...cameras.street, key: v.key + 1 }))}>
          서울 거리
        </button>
        <button
          onClick={() => {
            const road = urban.roads
              .filter((r) => r.motor && r.widthM >= 24 && r.coordinates.length >= 2)
              .sort((a, b) => {
                const distance = (r: typeof a) =>
                  r.coordinates.reduce(
                    (nearest, p) => Math.min(nearest, Math.hypot(p[0] - 6800, p[1] + 3500)),
                    Infinity
                  );
                return distance(a) - distance(b);
              })[0];
            if (road)
              setFocus((v) => ({
                center: road.coordinates[Math.floor(road.coordinates.length / 2)],
                distance: 80,
                key: v.key + 1,
              }));
          }}
        >
          도로 가까이
        </button>
        <button aria-pressed={hour === 14} onClick={() => setHour(14)}>
          낮
        </button>
        <button aria-pressed={hour === 22} onClick={() => setHour(22)}>
          밤
        </button>
        <label>
          X <input id="center-x" defaultValue="-1900" />
        </label>
        <label>
          Y <input id="center-y" defaultValue="-5770" />
        </label>
        <label>
          거리 <input id="distance" defaultValue="4200" />
        </label>
        <button
          onClick={() => {
            const number = (id: string) =>
              Number((document.getElementById(id) as HTMLInputElement).value);
            setFocus((v) => ({
              center: [number('center-x'), number('center-y')],
              distance: number('distance'),
              key: v.key + 1,
            }));
          }}
        >
          시점 적용
        </button>
        <output>
          {failure || error || details.error || urban.error || topography.error || traces.error
            ? '자료 오류'
            : busy || traces.loading
              ? '원 지도 준비 중'
              : '촬영 준비 완료'}
        </output>
      </header>
      <div id="capture" aria-label={`실제 게임 서울 지도 ${hour === 14 ? '낮' : '밤'} 촬영`}>
        <CityScene
          audio={audio}
          urbanClock={streetView && !floodMode ? streetClock : clock}
          streets={urban.roads}
          railTraffic={urban.railTraffic}
          railServices={urban.railServices}
          parking={urban.parking}
          population={urban.population}
          livePlaces={[]}
          historical={false}
          onFloodStats={noop}
          topography={topography}
          terrain={terrain}
          city={city}
          regions={[]}
          tiles={details.tiles}
          focus={focus}
          selected=""
          onCamera={onCamera}
          onNavigate={noop}
          labels={labels}
          onUnavailable={failed}
          ownDistrictId={null}
          sites={[]}
          groundCandidates={[]}
          occupiedSites={emptySet}
          installations={[]}
          installationBySite={emptyMap}
          selectedSite=""
          onSite={noop}
          onBuilding={noop}
          wetDistricts={[]}
          rainAmounts={emptyMap}
          rainCamera={camera}
          animateRain={streetView}
          preview={null}
          eligibleRoofs={emptySet}
          occupiedRoofs={emptySet}
          facilityType=""
          viewerId={null}
          publicAssets={[]}
          selectedAssetId=""
          onAsset={noop}
          onSurfaceError={noop}
          traceTiles={traces.tiles}
          onTraceError={failed}
        />
      </div>
    </>
  );
}
function App() {
  const { city, error } = useCity();
  return city ? <Scene city={city} /> : <p>{error || '서울 지도 불러오는 중'}</p>;
}
createRoot(document.getElementById('root')!).render(<App />);
