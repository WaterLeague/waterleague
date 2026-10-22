import { useCallback, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CityScene from '../src/domains/city/view/CityScene';
import { useCity, useCityTiles } from '../src/domains/city/controller/useCity';
import type { City, CityFocus } from '../src/domains/city/entity/city';
import { useTerrain } from '../src/domains/terrain/controller/useTerrain';
import { useUrbanData } from '../src/domains/urban/controller/useUrbanData';
import { useUrbanTime } from '../src/domains/urban/controller/useUrbanTime';
import { useTopography } from '../src/domains/topography/controller/useTopography';

if (!import.meta.env.DEV || !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
  throw new Error('로컬 촬영 전용');

const noop = () => {};
const emptySet = new Set<string>();
const emptyMap = new Map();
const labels = new Map<string, HTMLElement>();

function Scene({ city }: { city: City }) {
  const [focus, setFocus] = useState<CityFocus>({
    center: [-1900, -5770],
    distance: 4200,
    key: 0,
  });
  const [camera, setCamera] = useState(focus);
  const [hour, setHour] = useState(14);
  const [failure, setFailure] = useState(false);
  const { terrain, error } = useTerrain();
  const details = useCityTiles(city, camera);
  const urban = useUrbanData(details.tiles, camera.center, camera.distance);
  const topography = useTopography(camera.center, camera.distance, terrain, false);
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
          {failure || error || details.error || urban.error || topography.error
            ? '자료 오류'
            : busy
              ? '원 지도 준비 중'
              : '촬영 준비 완료'}
        </output>
      </header>
      <div id="capture" aria-label={`실제 게임 서울 지도 ${hour === 14 ? '낮' : '밤'} 촬영`}>
        <CityScene
          audio={audio}
          urbanClock={streetView ? streetClock : clock}
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
          onUnavailable={() => setFailure(true)}
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
          traceTiles={[]}
          onTraceError={noop}
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
