import { lazy, Suspense, useCallback, useState, useRef, useMemo } from 'react';
import { RotateCcw, MapPin, Layers3, CloudRain, Leaf, Grid2X2, House, List, X } from 'lucide-react';
import { useCity, useCityTiles } from '../controller/useCity';
import type { City, CityFocus, CityBuilding } from '../entity/city';
import type { CityEligibility } from '../dto/cityEligibilityDto';
import {
  buildingOpacity,
  otherDistrictOpacity,
  occupiedRoofSource,
} from '../service/siteVisibilityService';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { polygonPath } from '../../catalog/service/mapGeometryService';
import type { Account } from '../../account/entity/account';
import { useInstallations } from '../../installation/controller/useInstallations';
import { SharedDistrictPanel } from '../../installation/view/SharedDistrictPanel';
import type { SharedSite } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities, won } from '../../game/service/gameService';
import { loadSite, loadBuildingSite } from '../../installation/repository/installationRepository';
import { ApiError } from '../../../shared/exception/ApiError';
import { inBuildingRing } from '../service/buildingSelectionService';
import './shared-play.css';
import { siteKey } from '../../installation/entity/installation';
import { LiveRainfallPanel } from '../../rainfall/view/LiveRainfallPanel';
import { useHistorical } from '../../historical/controller/useHistorical';
import { HistoricalPanel, HistoricalTimeline } from '../../historical/view/HistoricalPanel';
import { useLiveRainfall } from '../../rainfall/controller/useLiveRainfall';
import { isRaining, observationFresh } from '../../rainfall/service/rainEffectService';
import { LiveRainPlan } from '../../rainfall/view/LiveRainPlan';
import { useReducedMotion } from '../../catalog/controller/useReducedMotion';
import { useWeekly } from '../../weekly/controller/useWeekly';
import { WeeklyBoard, scoreFormat } from '../../weekly/view/WeeklyBoard';
const CityScene = lazy(() => import('./CityScene'));
type PlayProps = {
  account: Account | null;
  onLogin: () => void;
  onAccount: (a: Account) => void;
  mode?: 'shared' | 'historical';
};
function Explorer({
  city,
  regions,
  eligibility,
  account,
  onLogin,
  onAccount,
  mode = 'shared',
}: { city: City; regions: CityPlayRegion[]; eligibility: CityEligibility } & PlayProps) {
  const researchMode = mode === 'historical';
  const weekly = useWeekly(!researchMode, account?.id ?? null);
  const districtScore = (id: string) => {
    if (weekly.error) return '순위 갱신 지연';
    const score = weekly.value?.current.districts.find((d) => d.districtId === id);
    return score?.rank ? `${score.rank}위 · ${scoreFormat.format(score.scoreM3)}m³` : '평가 대기';
  };
  const [selected, setSelected] = useState(researchMode ? (account?.districtId ?? '2419953') : '');
  const research = useHistorical(researchMode, selected, account);
  const ownDistrictId = researchMode ? null : account?.districtId;
  const viewerId = researchMode
    ? (account?.id ?? '00000000-0000-0000-0000-000000000000')
    : account?.id;
  const rainfall = useLiveRainfall(!researchMode);
  const reducedMotion = useReducedMotion();
  const historicalWetKey = research.wetKey;
  const wetDistricts = useMemo(() => {
    if (researchMode) {
      const ids = new Set(historicalWetKey.split(','));
      return city.districts.filter((d) => ids.has(d.id));
    }
    const ids = new Set(
      rainfall.value?.districts.filter((d) => isRaining(d, rainfall.now)).map((d) => d.districtId)
    );
    return city.districts.filter((d) => ids.has(d.id));
  }, [city, rainfall.value, rainfall.now, researchMode, historicalWetKey]);
  const wetIds = new Set(wetDistricts.map((d) => d.id));
  const unknownRainCount =
    rainfall.value?.districts.filter(
      (d) => !observationFresh(d, rainfall.now) || d.rainState === 'UNKNOWN'
    ).length ?? 25;
  const animateRain = rainfall.visible && !reducedMotion && (!researchMode || research.playing);
  const [site, setSite] = useState<SharedSite | null>(null);
  const selectedSite = site?.cellId ?? '';
  const [type, setType] = useState<FacilityType | ''>('');
  const [area, setArea] = useState('20');
  const [listOpen, setListOpen] = useState(false);
  const [vacant, setVacant] = useState(false);
  const [offset, setOffset] = useState(0);
  const [feedback, setFeedback] = useState('');
  const [selectionError, setSelectionError] = useState('');
  const selectionRequest = useRef(0);
  const [flat, setFlat] = useState(false),
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
  const sharedData = useInstallations(
    {
      districtId: selected,
      x: Math.round(camera.center[0] / 25) * 25,
      y: Math.round(camera.center[1] / 25) * 25,
      offset,
      type,
      vacant: researchMode ? false : vacant,
    },
    !researchMode
  );
  const researchMarkers = useMemo(
    () => research.drafts.map((d) => ({ ...d.marker, ownerId: viewerId! })),
    [research.drafts, viewerId]
  );
  const shared = {
    ...sharedData,
    installations: researchMode ? researchMarkers : sharedData.installations,
  };
  const occupiedRoofs = useMemo(
    () =>
      new Set(
        shared.installations
          .filter((i) => i.ownerId !== viewerId)
          .flatMap((i) => occupiedRoofSource(i.districtId, i.cellId, eligibility.legacySiteSources))
      ),
    [shared.installations, viewerId, eligibility]
  );
  const ownDistrict = city.districts.find((d) => d.id === ownDistrictId);
  function otherBuilding(b: CityBuilding) {
    return (
      !!ownDistrict &&
      !ownDistrict.polygons.some(
        (p) =>
          inBuildingRing(b.center, p[0]) && !p.slice(1).some((h) => inBuildingRing(b.center, h))
      )
    );
  }
  const ownInstallations = shared.installations.filter((i) => i.ownerId === viewerId);
  const remaining = researchMode
    ? research.remaining
    : 300000000 - ownInstallations.reduce((n, i) => n + i.cost, 0);
  const occupied = site
    ? shared.installations.find((i) => siteKey(i) === siteKey(site))
    : undefined;
  const visibleSites = useMemo(() => {
    const values = new Map(shared.sites.map((s) => [siteKey(s), s]));
    if (site) values.set(siteKey(site), site);
    return [...values.values()].filter(
      (s) =>
        s === site ||
        Math.hypot(s.center[0] - camera.center[0], s.center[1] - camera.center[1]) <
          camera.distance * 1.3
    );
  }, [shared.sites, site, camera]);
  const details = useCityTiles(city, camera);
  const labels = useRef(new Map<string, HTMLElement>());
  const onCamera = useCallback(
    (value: typeof camera) =>
      setCamera((previous) => {
        const threshold = Math.max(2, value.distance * 0.005);
        return Math.hypot(
          previous.center[0] - value.center[0],
          previous.center[1] - value.center[1]
        ) < threshold && Math.abs(previous.distance - value.distance) < threshold
          ? previous
          : value;
      }),
    []
  );
  const unavailable = useCallback(() => {
    setFailed(true);
    setFlat(true);
  }, []);
  function chooseSite(value: SharedSite) {
    selectionRequest.current++;
    setSelected(value.districtId);
    setCamera({ center: value.center, distance: Math.max(180, Math.sqrt(value.areaM2) * 3.5) });
    setSite(value);
    setType(value.allowedTypes.includes(type as FacilityType) ? type : value.allowedTypes[0]);
    setArea(String(Math.min(20, value.maxAreaM2)));
    setFeedback('');
    setListOpen(false);
    setOffset(0);
    setFocus((p) => ({
      center: value.center,
      distance: Math.max(180, Math.sqrt(value.areaM2) * 3.5),
      key: p.key + 1,
    }));
  }
  async function selectSite(key: string) {
    const request = ++selectionRequest.current;
    const found =
      shared.sites.find((s) => siteKey(s) === key) ?? (site && siteKey(site) === key ? site : null);
    setSelectionError('');
    if (found) {
      chooseSite(found);
      return;
    }
    const [districtId, cellId] = key.split(':');
    try {
      const value = await loadSite(districtId, cellId);
      if (request === selectionRequest.current) chooseSite(value);
    } catch {
      if (request === selectionRequest.current)
        setSelectionError('위치 정보를 불러오지 못했습니다. 다시 선택해 주세요.');
    }
  }
  async function selectBuilding(districtId: string, building: CityBuilding) {
    const request = ++selectionRequest.current;
    setSelected(districtId);
    setSite(null);
    setOffset(0);
    setFeedback('건물의 설치 후보 확인 중');
    setSelectionError('');
    try {
      const value = await loadBuildingSite(districtId, building.id);
      if (request === selectionRequest.current) chooseSite(value);
    } catch (error) {
      if (request !== selectionRequest.current) return;
      setFeedback('선택한 건물 · ' + building.id);
      setSelectionError(
        error instanceof ApiError && error.code === 'RESOURCE_NOT_FOUND'
          ? '이 건물은 공개자료 기준의 설치 후보에 포함되지 않았습니다. 주변의 표시된 후보를 선택해 주세요.'
          : '건물 정보를 불러오지 못했습니다. 다시 클릭해 주세요.'
      );
    }
  }
  function select(id: string) {
    const district = city.districts.find((d) => d.id === id);
    if (!district) return;
    const playRegion = regions.find((r) => r.districtId === id);
    setSelected(id);
    setCamera({
      center: playRegion?.center ?? district.center,
      distance: playRegion ? 1000 : 4800,
    });
    selectionRequest.current++;
    setSite(null);
    setOffset(0);
    setFeedback('');
    setFocus((p) => ({
      center: playRegion?.center ?? district.center,
      distance: playRegion ? 1000 : 4800,
      key: p.key + 1,
    }));
  }
  function reset() {
    setSelected('');
    setCamera({ center: [0, 0], distance: 35000 });
    setSite(null);
    setOffset(0);
    selectionRequest.current++;
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
          fill={ownDistrictId === d.id ? '#a3c884' : d.id === selected ? '#c4d6b4' : '#cbd5be'}
          opacity={!ownDistrictId || ownDistrictId === d.id ? 1 : otherDistrictOpacity}
          stroke="#809478"
          strokeWidth={d.id === ownDistrictId ? 75 : 20}
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
          <tspan x={d.center[0]}>{d.name}</tspan>
          {!researchMode && (
            <tspan x={d.center[0]} dy="1.3em" fontSize="0.72em">
              {districtScore(d.id)}
            </tspan>
          )}
        </text>
      ))}
      {!focus.overview &&
        details.tiles
          .flatMap((t) => t.buildings)
          .filter(
            (b) =>
              Math.abs(b.center[0] - focus.center[0]) < focus.distance * 1.2 &&
              Math.abs(b.center[1] - focus.center[1]) < focus.distance * 1.2
          )
          .map((b) => (
            <path
              key={b.id}
              d={polygonPath(b.polygons)}
              fill="#c6ccba"
              opacity={buildingOpacity(
                (!type || type === 'GREEN_ROOF') &&
                  eligibility.roofIds.has(b.id) &&
                  !occupiedRoofs.has(b.id),
                otherBuilding(b)
              )}
              stroke="#9eac96"
              strokeWidth={Math.max(0.5, focus.distance * 0.001)}
              onClick={() => {
                const d = city.districts.find((d) =>
                  d.polygons.some(
                    (p) =>
                      inBuildingRing(b.center, p[0]) &&
                      !p.slice(1).some((h) => inBuildingRing(b.center, h))
                  )
                );
                if (d) void selectBuilding(d.id, b);
              }}
            >
              <title>{b.id} · 건물 선택</title>
            </path>
          ))}
      {visibleSites.map((site) => {
        const installed = shared.installations.find((i) => siteKey(i) === siteKey(site));
        return (
          <path
            key={siteKey(site)}
            d={polygonPath([[site.coordinates]])}
            fill={
              site.districtId === selected && site.cellId === selectedSite
                ? '#ffd56d'
                : installed
                  ? '#327f56'
                  : site.kind === 'ROOF'
                    ? '#d9d8cb'
                    : '#b6c3ab'
            }
            stroke={
              site.districtId === selected && site.cellId === selectedSite ? '#b87a13' : '#6c8069'
            }
            strokeWidth={site.districtId === selected && site.cellId === selectedSite ? 2 : 0.5}
            opacity={buildingOpacity(
              (!type || site.allowedTypes.includes(type)) &&
                (!installed || installed.ownerId === viewerId),
              !!ownDistrictId && ownDistrictId !== site.districtId
            )}
            onClick={() => selectSite(siteKey(site))}
          >
            <title>
              {site.name} · {installed ? '설치됨' : '빈 위치'}
            </title>
          </path>
        );
      })}
      {shared.installations.map((i) => (
        <circle
          key={i.id}
          cx={i.center[0]}
          cy={-i.center[1]}
          r={focus.overview ? 95 : Math.max(2, focus.distance * 0.008)}
          fill="#327b4f"
          opacity={buildingOpacity(
            (!type || i.facilityType === type) && i.ownerId === viewerId,
            !!ownDistrictId && i.districtId !== ownDistrictId
          )}
          onClick={() => void selectSite(siteKey(i))}
        >
          <title>
            {i.ownerName} · {facilities[i.facilityType].name}
          </title>
        </circle>
      ))}
      <LiveRainPlan
        districts={wetDistricts}
        scale={focus.overview ? east - west : focus.distance * 2}
        animate={animateRain}
      />
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
    <main className="studio-layout play-layout shared-play-layout">
      <header className="play-hud">
        <div className="play-objective">
          <span>WATER LEAGUE / {researchMode ? '재해 모드' : '서울 공동 모드'}</span>
          <h1>{district?.name ?? '서울, 함께 바꾸는 물길'}</h1>
          <small>
            {researchMode
              ? '서울 전역의 공개 후보에 설계하고, 관측 강우로 비교하세요.'
              : '빈 위치를 찾아 설치하고, 우리 구의 빗물을 줄여보세요.'}
          </small>
        </div>
        <div className="play-resources">
          <span>
            {account ? '내 남은 예산' : '시작 예산'}
            <b>{won(remaining)}</b>
          </span>
          <span>
            {researchMode ? '연구 배치' : account ? '내 시설' : '서울 공유 시설'}
            <b>
              {researchMode
                ? research.current.length
                : account
                  ? ownInstallations.length
                  : shared.installations.length}
              <small> 곳</small>
            </b>
          </span>
        </div>
      </header>
      <div className="design-main shared-map-column">
        <div className="design-toolbar shared-toolbar">
          <label>
            <MapPin size={15} />
            <select
              aria-label="서울 자치구 선택"
              value={selected}
              onChange={(e) => (e.target.value ? select(e.target.value) : reset())}
            >
              <option value="">서울 전체</option>
              {city.districts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                  {d.id === ownDistrictId ? ' · 내 소속 구' : ''} ·{' '}
                  {shared.counts[d.id]?.toLocaleString('ko-KR') ?? '—'}곳
                </option>
              ))}
            </select>
          </label>
          <div>
            <button
              onClick={() => {
                if (account?.districtId) select(account.districtId);
                else onLogin();
              }}
            >
              <MapPin size={14} />내 소속 구
            </button>
            <button aria-expanded={listOpen} onClick={() => setListOpen((v) => !v)}>
              <List size={15} />
              위치 목록
            </button>
          </div>
        </div>
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
                  facilityType={type}
                  viewerId={viewerId ?? null}
                  city={city}
                  eligibleRoofs={eligibility.roofIds}
                  occupiedRoofs={occupiedRoofs}
                  regions={regions}
                  tiles={details.tiles}
                  focus={focus}
                  selected={selected}
                  near={camera.distance < 9000}
                  onCamera={onCamera}
                  labels={labels.current}
                  onUnavailable={unavailable}
                  ownDistrictId={ownDistrictId ?? null}
                  sites={visibleSites}
                  installations={shared.installations}
                  selectedSite={selectedSite}
                  onSite={selectSite}
                  onBuilding={selectBuilding}
                  wetDistricts={wetDistricts}
                  rainCamera={camera}
                  animateRain={animateRain}
                  preview={
                    site && !occupied && type && Number(area) > 0 && Number(area) <= site.maxAreaM2
                      ? {
                          site,
                          placement: {
                            cellId: site.cellId,
                            facilityType: type,
                            areaM2: Number(area),
                          },
                        }
                      : null
                  }
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
                  className={`city-district-label${d.id === selected ? ' selected' : ''}${ownDistrictId === d.id ? ' own-district' : ownDistrictId ? ' other-district' : ''}`}
                  onClick={() => select(d.id)}
                >
                  <span aria-hidden="true">● </span>
                  {d.name}
                  {ownDistrictId === d.id ? ' · 내 구' : ''}{' '}
                  {wetIds.has(d.id) && (
                    <CloudRain
                      size={13}
                      aria-label={researchMode ? '재해 관측 강우 재생' : '최근 관측 비 감지'}
                    />
                  )}
                  <small>
                    {shared.installations.filter((i) => i.districtId === d.id).length}곳
                    {!researchMode && ` · ${districtScore(d.id)}`}
                  </small>
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
                  {!researchMode && ` · ${districtScore(r.districtId)}`}
                </button>
              ))}
            </div>
          )}
          <div className="city-map-top">
            <span>
              <Layers3 size={14} />{' '}
              {researchMode
                ? '25개 구 · 재해 모드'
                : ownDistrict
                  ? `내 소속 구 · ${ownDistrict.name}`
                  : '25개 구 · 공동 지도'}
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
          <div className="city-weather-badge" role="status">
            <CloudRain size={15} />
            <span>
              {researchMode
                ? research.at
                  ? new Date(research.at).toLocaleTimeString('ko-KR', {
                      hour: '2-digit',
                      minute: '2-digit',
                      timeZone: 'Asia/Seoul',
                    }) +
                    ' · 1분 ' +
                    research.rainMm +
                    'mm'
                  : '재해 강우 불러오는 중'
                : rainfall.error
                  ? '현재 강수 확인 불가'
                  : !rainfall.value
                    ? '기상청 관측 연결 중'
                    : wetDistricts.length
                      ? `${wetDistricts.length}개 구에서 비 감지`
                      : unknownRainCount === 25
                        ? '현재 강수 확인 불가'
                        : '현재 비 감지 구 없음'}
              {!researchMode && rainfall.value && unknownRainCount > 0 && unknownRainCount < 25
                ? ` · ${unknownRainCount}개 구 미확인`
                : ''}
              <small>
                {researchMode
                  ? '재해 당시 관측 재생 · 현재 날씨 아님'
                  : '구별 관측소 기준 · 1분마다 갱신'}
                {wetDistricts.length > 0 ? ' · 빗줄기는 표현용' : ''}
              </small>
            </span>
          </div>
          <div className="shared-map-legend">
            <span>
              <i className="available" />
              {type ? facilities[type].name + ' 후보' : '설치 후보'}
            </span>
            <span>
              <i className="unavailable" />
              {researchMode
                ? '선택 시설 설치 불가'
                : type
                  ? '선택 시설 설치 불가·점유'
                  : '후보 제외·다른 회원 점유'}
            </span>
            {ownDistrict && (
              <span>
                <i className="other" />
                다른 구 · 조회만
              </span>
            )}
          </div>
          {listOpen && (
            <div
              className="shared-location-list"
              onKeyDown={(e) => {
                if (e.key === 'Escape') setListOpen(false);
              }}
            >
              <div className="shared-list-heading">
                <strong>{district?.name ?? '구 선택'} · 설치 위치</strong>
                <button aria-label="위치 목록 닫기" onClick={() => setListOpen(false)}>
                  <X size={16} />
                </button>
              </div>
              {!researchMode && (
                <label className="shared-vacant">
                  <input
                    type="checkbox"
                    checked={vacant}
                    onChange={(e) => {
                      setVacant(e.target.checked);
                      setOffset(0);
                    }}
                  />
                  빈 위치만
                </label>
              )}
              {!selected ? (
                <p>먼저 구를 선택해 주세요.</p>
              ) : shared.siteBusy ? (
                <p role="status">지도 주변 후보 조회 중</p>
              ) : shared.siteError ? (
                <p role="alert">
                  {shared.siteError}
                  <button onClick={shared.retrySites}>다시 조회</button>
                </p>
              ) : (
                <>
                  <p>
                    조건에 맞는 {shared.matchedCount.toLocaleString('ko-KR')}곳 · 지도 중심에서
                    가까운 순
                  </p>
                  <div className="shared-location-items">
                    {shared.sites.map((s) => {
                      const installed = shared.installations.find((i) => siteKey(i) === siteKey(s));
                      return (
                        <button
                          key={siteKey(s)}
                          aria-pressed={site?.cellId === s.cellId}
                          onClick={() => chooseSite(s)}
                        >
                          <span>
                            {s.kind === 'ROOF' ? <House size={15} /> : <Grid2X2 size={15} />}
                            <strong>{s.name}</strong>
                          </span>
                          <small>
                            {installed ? installed.ownerName + ' · 설치됨' : '빈 위치'} · 최대{' '}
                            {s.maxAreaM2.toLocaleString('ko-KR')} m²
                          </small>
                        </button>
                      );
                    })}
                  </div>
                  <div className="shared-list-pages">
                    <button
                      disabled={offset === 0}
                      onClick={() => setOffset((v) => Math.max(0, v - 200))}
                    >
                      이전
                    </button>
                    <span>
                      {shared.matchedCount ? offset + 1 : 0}–
                      {Math.min(offset + 200, shared.matchedCount)}
                    </span>
                    <button
                      disabled={offset + 200 >= shared.matchedCount}
                      onClick={() => setOffset((v) => v + 200)}
                    >
                      다음
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
          <div className="shared-map-count" role="status">
            {shared.siteError ? (
              <>
                <span>설치 후보 조회 실패</span>
                <button onClick={shared.retrySites}>다시 조회</button>
              </>
            ) : Object.keys(shared.counts).length === 0 ? (
              '설치 후보 조회 중'
            ) : (
              <>
                {selected
                  ? `${shared.counts[selected].toLocaleString('ko-KR')}곳의 공개 후보`
                  : `서울 ${Object.values(shared.counts)
                      .reduce((a, b) => a + b, 0)
                      .toLocaleString('ko-KR')}곳의 공개 후보`}
                <small>
                  {selected
                    ? '지도 이동 · 확대 또는 위치 목록에서 선택'
                    : '구를 선택하면 설치 후보가 표시됩니다'}
                </small>
              </>
            )}
          </div>
          <div className="facility-dock" role="group" aria-label="시설 선택">
            {(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF'] as const).map((t) => {
              const Icon =
                t === 'RAIN_GARDEN' ? Leaf : t === 'PERMEABLE_PAVEMENT' ? Grid2X2 : House;
              return (
                <button
                  key={t}
                  className={type === t ? 'selected' : ''}
                  aria-pressed={type === t}
                  onClick={() => {
                    setType(t);
                    setOffset(0);
                    setSite(null);
                    setFeedback('');
                    if (ownDistrictId && selected !== ownDistrictId) select(ownDistrictId);
                    setListOpen(true);
                  }}
                >
                  <Icon size={20} />
                  <span>{facilities[t].name}</span>
                </button>
              );
            })}
            <button
              aria-pressed={!type}
              onClick={() => {
                setType('');
                setOffset(0);
              }}
            >
              전체
            </button>
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
        {researchMode ? (
          <HistoricalTimeline state={research} />
        ) : (
          <details className="shared-rain-details">
            <summary>
              <CloudRain size={15} />
              실시간 강우 · 관측 정보 보기
            </summary>
            <LiveRainfallPanel districtId={selected} rainfall={rainfall} />
          </details>
        )}
      </div>
      {researchMode ? (
        <HistoricalPanel
          state={research}
          site={site}
          type={type}
          area={area}
          onType={setType}
          onArea={setArea}
          onLogin={onLogin}
          authenticated={!!account}
          error={selectionError}
        />
      ) : (
        <SharedDistrictPanel
          account={account}
          districtId={selected}
          districtName={district?.name ?? ''}
          site={site}
          occupied={occupied}
          type={type}
          area={area}
          onType={setType}
          onArea={setArea}
          remaining={remaining}
          busy={shared.busy}
          error={shared.error || selectionError}
          feedback={feedback}
          onInstall={async (s, t, a) => {
            const ok = await shared.install(s, t, a);
            if (ok) setFeedback('설치 완료 · 모두의 지도에 반영됐습니다');
            return ok;
          }}
          onRemove={async (id) => {
            const ok = await shared.remove(id);
            if (ok) setFeedback('철거 완료 · 빈 위치로 돌아왔습니다');
            return ok;
          }}
          onLogin={onLogin}
          onAccount={onAccount}
          onLocate={() => {
            if (ownDistrictId) select(ownDistrictId);
          }}
        />
      )}
      {!researchMode && (
        <WeeklyBoard
          value={weekly.value}
          error={weekly.error}
          ownDistrictId={ownDistrictId ?? null}
          onDistrict={select}
        />
      )}
      <footer className="city-source-note">
        공개자료 기준 {city.sourceDate} · 건물 높이는 태그·층수 환산·표현용 가정 · 지면 평탄화 ·
        실제 침수 깊이 표시 아님
      </footer>
    </main>
  );
}
export function CityExplorer({ account, onLogin, onAccount, mode = 'shared' }: PlayProps) {
  const { city, regions, eligibility, error, retry } = useCity();
  if (!city || !eligibility)
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
      key={mode}
      mode={mode}
      city={city}
      eligibility={eligibility}
      regions={regions}
      account={account}
      onLogin={onLogin}
      onAccount={onAccount}
    />
  );
}
