import { lazy, Suspense, useCallback, useState, useRef } from 'react';
import { ArrowRight, Search, RotateCcw, MapPin, Layers3 } from 'lucide-react';
import { useCity, useCityTiles } from '../controller/useCity';
import type { City, CityFocus } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { polygonPath } from '../../catalog/service/mapGeometryService';
const CityScene = lazy(() => import('./CityScene'));
type PlayProps = { busy: boolean; onPlay: (modelHash?: string) => void };
function Explorer({
  city,
  regions,
  onPlay,
  busy,
}: { city: City; regions: CityPlayRegion[] } & PlayProps) {
  const [selected, setSelected] = useState(''),
    [query, setQuery] = useState(''),
    [flat, setFlat] = useState(false),
    [failed, setFailed] = useState(false);
  const [focus, setFocus] = useState<CityFocus>({
    center: [0, 0],
    distance: 35000,
    key: 0,
    overview: true,
  });
  const [camera, setCamera] = useState<{ center: [number, number]; distance: number }>({
    center: [0, 0],
    distance: 35000,
  });
  const details = useCityTiles(city, camera);
  const labels = useRef(new Map<string, HTMLElement>());
  const onCamera = useCallback((value: typeof camera) => setCamera(value), []);
  const unavailable = useCallback(() => {
    setFailed(true);
    setFlat(true);
  }, []);
  function select(id: string) {
    const district = city.districts.find((d) => d.id === id);
    if (!district) return;
    const playRegion = regions.find((r) => r.districtId === id);
    setSelected(id);
    setFocus((p) => ({
      center: playRegion?.center ?? district.center,
      distance: playRegion ? 2400 : 4800,
      key: p.key + 1,
    }));
  }
  function reset() {
    setSelected('');
    setFocus((p) => ({ center: [0, 0], distance: 35000, key: p.key + 1, overview: true }));
  }
  const district = city.districts.find((d) => d.id === selected);
  const region = regions.find((r) => r.districtId === selected);
  const [west, south, east, north] = city.bounds;
  const plan = (
    <svg
      className="city-plan"
      viewBox={`${west - 1000} ${-north - 1000} ${east - west + 2000} ${north - south + 2000}`}
      role="group"
      aria-label="서울 25개 구 플레이 지도"
    >
      <path d={polygonPath(city.boundary)} fill="#dfe3cf" />
      {city.districts.map((d) => (
        <path
          key={d.id}
          d={polygonPath(d.polygons)}
          fill={d.id === selected ? '#b6cda4' : '#dfe3cf'}
          stroke="#809478"
          strokeWidth={30}
          onClick={() => select(d.id)}
        >
          <title>{d.name}</title>
        </path>
      ))}
      {city.surfaces
        .filter((s) => s.kind === 'water')
        .map((s, i) => (
          <path key={i} d={polygonPath(s.polygons)} fill="#81b1ba" />
        ))}
      {city.districts.map((d) => (
        <text
          key={d.id}
          x={d.center[0]}
          y={-d.center[1]}
          textAnchor="middle"
          fontSize={420}
          fill="#233c35"
        >
          {d.name}
        </text>
      ))}
      {regions.map((r) => (
        <g
          key={r.mapId}
          role="button"
          tabIndex={0}
          aria-label={`${r.districtName} 대표 블록 선택`}
          aria-pressed={r.districtId === selected}
          className="city-plan-pin"
          onClick={() => select(r.districtId)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              select(r.districtId);
            }
          }}
        >
          <circle
            cx={r.center[0]}
            cy={-r.center[1]}
            r={r.districtId === selected ? 230 : 160}
            fill={r.districtId === selected ? '#173d29' : '#52734b'}
            stroke="#fffdf2"
            strokeWidth={60}
          />
          <title>{r.districtName} · 대표 블록 플레이 가능</title>
        </g>
      ))}
    </svg>
  );
  return (
    <main className="city-explorer">
      <aside className="city-sidebar">
        <div className="city-heading">
          <span>WATER LEAGUE / SEOUL</span>
          <h1>
            서울, 물길을
            <br />
            <em>바꾸는 선택.</em>
          </h1>
          <p>
            플레이할 구를 고르고
            <br />
            대표 블록의 빗물 설계에 도전하세요.
          </p>
        </div>
        <label className="city-search">
          <Search size={17} />
          <input
            aria-label="서울 자치구 검색"
            placeholder="우리 동네 찾기"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <p className="city-play-count">{regions.length}개 구 · 대표 블록 플레이 가능</p>
        <div className="city-districts" aria-label="플레이할 서울 자치구 선택">
          {city.districts
            .filter((d) => d.name.includes(query.trim()))
            .map((d) => (
              <button
                key={d.id}
                aria-pressed={d.id === selected}
                onClick={() => select(d.id)}
                title={`${d.name} 대표 블록 선택`}
              >
                {d.name}
              </button>
            ))}
        </div>
        {district && (
          <div className="city-selected">
            <MapPin size={15} />
            <strong>{district.name}</strong>
            <span>대표 블록 선택됨</span>
          </div>
        )}
        <div className="city-mission">
          <span className="city-mission-kicker">{region ? '선택한 지역 도전' : '빠른 시작'}</span>
          <h2>{region ? `${region.districtName} · 대표 블록` : '성수 · 연무장길'}</h2>
          <p>
            {region ? '옥상 8곳 · 지상 5곳' : '관측 강우와 3종 시설로'}
            <br />
            {region?.defaultRainfall
              ? `${region.defaultRainfall.stationName} 관측소 · ${region.defaultRainfall.distanceKm} km`
              : '성동 관측 강우로 설계에 도전하세요.'}
          </p>
          <button disabled={busy} onClick={() => onPlay(region?.defaultModelHash)}>
            {busy ? '도전 준비 중' : `${region?.districtName ?? '성수'}에서 도전`}{' '}
            <ArrowRight size={18} />
          </button>
          <button
            className="city-locate"
            onClick={() => {
              setFocus((p) => ({
                center: region?.center ?? city.playAreas[0].center,
                distance: 800,
                key: p.key + 1,
              }));
            }}
          >
            지도에서 보기 <MapPin size={13} />
          </button>
        </div>
        <small className="city-model-note">
          25개 구의 대표 블록에서 플레이할 수 있습니다. 인근 관측 강우와 성동 공통 강우를 선택하며,
          구 전체 유역 계산은 아닙니다.
        </small>
      </aside>
      <section className="city-stage" aria-label="서울 전역 3D 지도">
        {flat ? (
          plan
        ) : (
          <ErrorBoundary fallback={plan} onError={unavailable}>
            <Suspense
              fallback={
                <div className="empty-state" role="status">
                  서울 3D 지도 구성 중
                </div>
              }
            >
              <CityScene
                city={city}
                regions={regions}
                tiles={details.tiles}
                focus={focus}
                selected={selected}
                near={camera.distance < 9000}
                onCamera={onCamera}
                labels={labels.current}
                onUnavailable={unavailable}
              />
            </Suspense>
          </ErrorBoundary>
        )}
        {!flat && (
          <div className="city-map-labels" aria-label="지도에서 자치구 선택">
            {city.districts.map((d) => (
              <button
                key={d.id}
                ref={(element) => {
                  if (element) labels.current.set(d.id, element);
                  else labels.current.delete(d.id);
                }}
                className={`city-district-label${d.id === selected ? ' selected' : ''}`}
                onClick={() => select(d.id)}
              >
                <span aria-hidden="true">● </span>
                {d.name}
              </button>
            ))}
            {regions.map((r) => (
              <button
                key={r.mapId}
                ref={(element) => {
                  if (element) labels.current.set(r.mapId, element);
                  else labels.current.delete(r.mapId);
                }}
                className={`city-play-pin${r.districtId === selected ? ' selected' : ''}`}
                disabled={busy}
                onClick={() => onPlay(r.defaultModelHash)}
                aria-label={`${r.districtName} 대표 블록에서 도전`}
              >
                ● {r.districtName} 플레이 →
              </button>
            ))}
          </div>
        )}
        <div className="city-map-top">
          <span>
            <Layers3 size={14} /> {regions.length}개 구 플레이
          </span>
          <div>
            <button
              aria-pressed={!flat}
              onClick={() => {
                setFailed(false);
                setFlat(false);
              }}
            >
              3D
            </button>
            <button aria-pressed={flat} onClick={() => setFlat(true)}>
              2D
            </button>
            <button onClick={reset} aria-label="서울 전체 보기">
              <RotateCcw size={15} />
            </button>
          </div>
        </div>
        <div className="city-map-bottom">
          <div>
            <b>{city.buildingCount.toLocaleString('ko-KR')}개 건물 경계</b>
            <span>
              {flat
                ? '목록 또는 구역 선택'
                : details.busy
                  ? '주변 건물 불러오는 중'
                  : camera.distance > 6500
                    ? '확대하면 주변 건물을 자세히 볼 수 있습니다'
                    : `${details.tiles.reduce((n, t) => n + t.buildings.length, 0).toLocaleString('ko-KR')}개 주변 건물 표시`}
            </span>
          </div>
          <small>
            회전 · 드래그
            <br />
            이동 · 오른쪽 드래그 / 확대 · 스크롤
          </small>
        </div>
        {(details.error || failed) && (
          <p className="city-error" role="alert">
            {failed ? '3D 연결이 끊겨 2D 지도로 전환했습니다.' : details.error}
          </p>
        )}
        <a className="city-credit" href={city.licenseUrl} target="_blank" rel="noreferrer">
          {city.attribution}
        </a>
      </section>
      <footer className="city-source-note">
        공개자료 기준 {city.sourceDate} · 건물 높이는 태그·층수 환산·표현용 가정 · 지면 평탄화 ·
        실제 침수 깊이 표시 아님
      </footer>
    </main>
  );
}
export function CityExplorer({ onPlay, busy }: PlayProps) {
  const { city, regions, error, retry } = useCity();
  if (!city)
    return (
      <main className="empty-state" role={error ? 'alert' : 'status'}>
        <h1>{error ? '서울 지도를 불러오지 못했습니다' : '서울 지도를 준비하고 있습니다'}</h1>
        <p>{error || '저장된 공개 공간자료를 불러오는 중'}</p>
        {error && (
          <button className="outline-button" onClick={retry}>
            다시 불러오기
          </button>
        )}
      </main>
    );
  return <Explorer city={city} regions={regions} onPlay={onPlay} busy={busy} />;
}
