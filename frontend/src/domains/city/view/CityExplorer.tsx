import { lazy, Suspense, useCallback, useState, useRef } from 'react';
import { Search, RotateCcw, MapPin, Layers3 } from 'lucide-react';
import { useCity, useCityTiles } from '../controller/useCity';
import type { City, CityFocus } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { polygonPath } from '../../catalog/service/mapGeometryService';
import type { Account } from '../../account/entity/account';
import { useInstallations } from '../../installation/controller/useInstallations';
import { SharedDistrictPanel } from '../../installation/view/SharedDistrictPanel';
import { siteKey } from '../../installation/entity/installation';
import { LiveRainfallPanel } from '../../rainfall/view/LiveRainfallPanel';
const CityScene = lazy(() => import('./CityScene'));
type PlayProps = { account: Account | null; onLogin: () => void; onAccount: (a: Account) => void };
function Explorer({
  city,
  regions,
  account,
  onLogin,
  onAccount,
}: { city: City; regions: CityPlayRegion[] } & PlayProps) {
  const shared = useInstallations();
  const [selectedSite, setSelectedSite] = useState('');
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
  function selectSite(key: string) {
    const site = shared.sites.find((s) => siteKey(s) === key);
    if (!site) return;
    setSelected(site.districtId);
    setSelectedSite(site.cellId);
    setFocus((p) => ({ center: site.center, distance: 260, key: p.key + 1 }));
  }
  function select(id: string) {
    const district = city.districts.find((d) => d.id === id);
    if (!district) return;
    const playRegion = regions.find((r) => r.districtId === id);
    setSelected(id);
    setSelectedSite('');
    setFocus((p) => ({
      center: playRegion?.center ?? district.center,
      distance: playRegion ? 1000 : 4800,
      key: p.key + 1,
    }));
  }
  function reset() {
    setSelected('');
    setFocus((p) => ({ center: [0, 0], distance: 35000, key: p.key + 1, overview: true }));
  }
  const district = city.districts.find((d) => d.id === selected);
  const [west, south, east, north] = city.bounds;
  const plan = (
    <svg
      className="city-plan"
      viewBox={
        focus.overview
          ? `${west - 1000} ${-north - 1000} ${east - west + 2000} ${north - south + 2000}`
          : `${focus.center[0] - focus.distance} ${-focus.center[1] - focus.distance} ${focus.distance * 2} ${focus.distance * 2}`
      }
      role="group"
      aria-label="서울 25개 구 플레이 지도"
    >
      <path d={polygonPath(city.boundary)} fill="#eef0e6" />
      {city.districts.map((d) => (
        <path
          key={d.id}
          d={polygonPath(d.polygons)}
          fill={d.id === selected ? '#b6cda4' : '#dfe3cf'}
          opacity={!account?.districtId || account.districtId === d.id ? 1 : 0.35}
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
          fontSize={focus.overview ? 420 : focus.distance * 0.035}
          fill="#233c35"
        >
          {d.name}
        </text>
      ))}
      {shared.sites
        .filter(
          (site) =>
            site.districtId === selected ||
            shared.installations.some((i) => siteKey(i) === siteKey(site))
        )
        .map((site) => {
          const installed = shared.installations.some((i) => siteKey(i) === siteKey(site));
          return (
            <path
              key={siteKey(site)}
              d={polygonPath([[site.coordinates]])}
              fill={installed ? '#327f56' : '#d7a743'}
              stroke="#183c2d"
              strokeWidth={2}
              opacity={!account?.districtId || account.districtId === site.districtId ? 1 : 0.35}
              onClick={() => selectSite(siteKey(site))}
            >
              <title>
                {site.name} · {installed ? '설치됨' : '빈 위치'}
              </title>
            </path>
          );
        })}
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
            r={focus.overview ? 160 : 8}
            fill={r.districtId === selected ? '#173d29' : '#52734b'}
            stroke="#fffdf2"
            strokeWidth={focus.overview ? 60 : 2}
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
            우리 구의 빗물을 줄이고
            <br />
            서울의 주간 순위에 함께 도전하세요.
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
        <LiveRainfallPanel districtId={selected} />
        <p className="city-play-count">25개 구 · 공유 시설 {shared.installations.length}곳</p>
        <div className="city-districts" aria-label="서울 자치구 상태 조회">
          {city.districts
            .filter((d) => d.name.includes(query.trim()))
            .map((d) => (
              <button
                key={d.id}
                aria-pressed={d.id === selected}
                onClick={() => select(d.id)}
                title={`${d.name} 설치 상태 조회`}
              >
                {d.name}{' '}
                <small>{shared.installations.filter((i) => i.districtId === d.id).length}곳</small>
              </button>
            ))}
        </div>
        {district && (
          <div className="city-selected">
            <MapPin size={15} />
            <strong>{district.name}</strong>
            <span>{account?.districtId === selected ? '내 소속 구' : '설치 상태 조회'}</span>
          </div>
        )}
        {account?.districtId && (
          <button className="city-locate" onClick={() => select(account.districtId!)}>
            내 소속 구로 이동 <MapPin size={13} />
          </button>
        )}
        <SharedDistrictPanel
          account={account}
          districtId={selected}
          districtName={district?.name ?? ''}
          sites={shared.sites.filter((s) => s.districtId === selected)}
          installations={shared.installations.filter((i) => i.districtId === selected)}
          selected={selectedSite}
          onSelect={(id) => selectSite(`${selected}:${id}`)}
          busy={shared.busy}
          error={shared.error}
          onInstall={shared.install}
          onRemove={shared.remove}
          onLogin={onLogin}
          onAccount={onAccount}
        />
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
                ownDistrictId={account?.districtId ?? null}
                sites={shared.sites}
                installations={shared.installations}
                selectedSite={selectedSite}
                onSite={selectSite}
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
                {d.name}{' '}
                <small>{shared.installations.filter((i) => i.districtId === d.id).length}곳</small>
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
                onClick={() => select(r.districtId)}
                aria-label={`${r.districtName} 공유 설치 상태 보기`}
              >
                ● {r.districtName} ·{' '}
                {shared.installations.filter((i) => i.districtId === r.districtId).length}곳
              </button>
            ))}
          </div>
        )}
        <div className="city-map-top">
          <span>
            <Layers3 size={14} /> 25개 구 · 공동 지도
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
export function CityExplorer({ account, onLogin, onAccount }: PlayProps) {
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
  return (
    <Explorer
      city={city}
      regions={regions}
      account={account}
      onLogin={onLogin}
      onAccount={onAccount}
    />
  );
}
