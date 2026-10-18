import { lazy, Suspense, useEffect, useCallback, useState, useRef, useMemo } from 'react';
import { RotateCcw, MapPin, Layers3, CloudRain, List, X, Trophy, ArrowLeft } from 'lucide-react';
import { useCity, useCityTiles } from '../controller/useCity';
import { useMapLabelWheel } from '../controller/useMapLabelWheel';
import type { City, CityFocus, CityBuilding } from '../entity/city';
import type { CityEligibility } from '../dto/cityEligibilityDto';
import { occupiedRoofSource } from '../service/siteVisibilityService';
import { siteFocus } from '../service/siteFocusService';
import type { PlanView } from '../service/planNavigationService';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { CityPlan } from './CityPlan';
import type { Account } from '../../account/entity/account';
import { useInstallations } from '../../installation/controller/useInstallations';
import { SharedDistrictPanel } from '../../installation/view/SharedDistrictPanel';
import type { SharedSite } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities, won } from '../../game/service/gameService';
import { loadSite, loadBuildingSite } from '../../installation/repository/installationRepository';
import { ApiError } from '../../../shared/exception/ApiError';
import './shared-play.css';
import { siteKey } from '../../installation/entity/installation';
import { LiveRainfallPanel } from '../../rainfall/view/LiveRainfallPanel';
import { useHistorical } from '../../historical/controller/useHistorical';
import { HistoricalPanel, HistoricalTimeline } from '../../historical/view/HistoricalPanel';
import { useLiveRainfall } from '../../rainfall/controller/useLiveRainfall';
import { isRaining, observationFresh } from '../../rainfall/service/rainEffectService';
import { useReducedMotion } from '../../catalog/controller/useReducedMotion';
import { useBudget } from '../../budget/controller/useBudget';
import { useWeekly } from '../../weekly/controller/useWeekly';
import { WeeklyBoard, scoreFormat } from '../../weekly/view/WeeklyBoard';
import { useTerrain } from '../../terrain/controller/useTerrain';
import { GameClock } from '../../game/view/GameClock';
import { useInfrastructure } from '../../infrastructure/controller/useInfrastructure';
import { visibleInfrastructure } from '../../infrastructure/service/infrastructureService';
import { InfrastructurePanel } from '../../infrastructure/view/InfrastructurePanel';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { useFloodTraces } from '../../floodtrace/controller/useFloodTraces';
import { FloodTraceControls } from '../../floodtrace/view/FloodTraceControls';
import { useSurfacePlayback } from '../../surface/controller/useSurfacePlayback';
import { SurfaceControls } from '../../surface/view/SurfaceControls';
import type { SurfaceMetric, SurfaceSource } from '../../surface/entity/surface';
import { FacilityExpansionPanel } from '../../watershed/view/FacilityExpansionPanel';
const CityScene = lazy(() => import('./CityScene'));
type PlayProps = {
  account: Account | null;
  onLogin: () => void;
  onAccount: (a: Account) => void;
  mode?: 'shared' | 'historical';
  initialDistrictId?: string;
  eventId?: string;
  onExit?: () => void;
};
function Explorer({
  city,
  regions,
  eligibility,
  account,
  onLogin,
  onAccount,
  mode = 'shared',
  initialDistrictId = '',
  eventId = '',
  onExit,
}: { city: City; regions: CityPlayRegion[]; eligibility: CityEligibility } & PlayProps) {
  const researchMode = mode === 'historical';
  const { terrain, error: terrainError } = useTerrain();
  const infrastructure = useInfrastructure();
  const [infrastructureOpen, setInfrastructureOpen] = useState(false);
  const [facilityExpansionOpen, setFacilityExpansionOpen] = useState(false);
  const [assetsEnabled, setAssetsEnabled] = useState(true);
  const [tracesEnabled, setTracesEnabled] = useState(false);
  const [surfaceEnabled, setSurfaceEnabled] = useState(false);
  const [surfaceMetric, setSurfaceMetric] = useState<SurfaceMetric>('depth');
  const [surfaceIndex, setSurfaceIndex] = useState<number | null>(null);
  const [surfaceRenderError, setSurfaceRenderError] = useState(false);
  const surfaceFailed = useCallback(() => setSurfaceRenderError(true), []);
  const [referenceTraceEvent, setReferenceTraceEvent] = useState('seoul-20220808');
  const [traceRenderError, setTraceRenderError] = useState(false);
  const traceFailed = useCallback(() => setTraceRenderError(true), []);
  const [selectedAssetId, setSelectedAssetId] = useState('');
  const [budgetRevision, setBudgetRevision] = useState(0);
  const budget = useBudget(budgetRevision, account?.id ?? null);
  const weekly = useWeekly(!researchMode, account?.id ?? null);
  const districtScore = (id: string) => {
    if (weekly.error) return '순위 갱신 지연';
    const score = weekly.value?.current.districts.find((d) => d.districtId === id);
    return score?.rank ? `${score.rank}위 · ${scoreFormat.format(score.scoreM3)}m³` : '평가 대기';
  };
  const [selected, setSelected] = useState(
    researchMode ? (account?.districtId ?? '2419953') : initialDistrictId
  );
  const research = useHistorical(researchMode, selected, account, budget.value, eventId);
  const [rankingOpen, setRankingOpen] = useState(false);
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
  const rainAmounts = useMemo(
    () =>
      new Map<string, number | null>(
        researchMode
          ? (research.event?.regions.map(
              (r) => [r.districtId, r.depthsMm[research.index] ?? null] as const
            ) ?? [])
          : (rainfall.value?.districts.map((d) => [d.districtId, d.oneMinuteMm] as const) ?? [])
      ),
    [researchMode, research.event, research.index, rainfall.value]
  );
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
  useEffect(() => {
    if (initialDistrictId && !researchMode) select(initialDistrictId);
  }, [initialDistrictId, researchMode]);
  const stage = useRef<HTMLElement>(null);
  const [camera, setCamera] = useState<PlanView>({
    center: [0, 0],
    distance: 35000,
  });
  const navigationCamera = useRef(camera);
  const traceEventId = researchMode ? eventId : referenceTraceEvent;
  const traces = useFloodTraces(tracesEnabled, traceEventId, camera);
  const publicAssets = useMemo(
    () =>
      assetsEnabled && infrastructure.catalog
        ? visibleInfrastructure(
            infrastructure.catalog.assets,
            camera.center,
            camera.distance,
            selectedAssetId
          )
        : [],
    [infrastructure.catalog, assetsEnabled, camera, selectedAssetId]
  );
  const selectAsset = useCallback((asset: InfrastructureAsset) => {
    selectionRequest.current++;
    setSite(null);
    setSelectionError('');
    setFeedback('');
    setSelected(asset.districtId);
    setSelectedAssetId(asset.id);
    setInfrastructureOpen(true);
    setFacilityExpansionOpen(false);
    setAssetsEnabled(true);
    setFocus((previous) => ({ center: asset.center, distance: 1000, key: previous.key + 1 }));
  }, []);
  const onNavigate = useCallback((value: typeof camera) => {
    navigationCamera.current = value;
  }, []);
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
  const installationBySite = useMemo(
    () => new Map(shared.installations.map((i) => [siteKey(i), i])),
    [shared.installations]
  );
  const occupiedRoofs = useMemo(
    () =>
      new Set(
        shared.installations
          .filter((i) => i.ownerId !== viewerId)
          .flatMap((i) => occupiedRoofSource(i.districtId, i.cellId, eligibility.legacySiteSources))
      ),
    [shared.installations, viewerId, eligibility]
  );
  const ownInstallations = shared.installations.filter((i) => i.ownerId === viewerId);
  const remaining = researchMode ? research.remaining : (budget.value?.remainingKrw ?? 0);
  const occupied = site ? installationBySite.get(siteKey(site)) : undefined;
  const surfaceSource: SurfaceSource | null = researchMode
    ? research.job?.state === 'SUCCEEDED' && research.currentResult
      ? { kind: 'historical', id: research.job.id }
      : null
    : occupied?.ownerId === account?.id && occupied
      ? { kind: 'installation', id: occupied.id }
      : null;
  const surface = useSurfacePlayback(
    surfaceEnabled,
    surfaceSource,
    account?.id ?? null,
    researchMode ? research.at : null,
    camera,
    city,
    researchMode ? null : surfaceIndex
  );
  useEffect(() => {
    setSurfaceIndex(null);
    setSurfaceRenderError(false);
  }, [surfaceSource?.kind, surfaceSource?.id, account?.id]);
  const seekSurface = (index: number) => {
    if (researchMode && surface.catalog && research.at) {
      const at = Date.parse(surface.catalog.startUtc) + surface.catalog.timesSeconds[index] * 1000;
      research.setElapsedSeconds(research.elapsedSeconds + (at - Date.parse(research.at)) / 1000);
    } else setSurfaceIndex(index);
  };
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
  const labelLayer = useRef<HTMLDivElement>(null);
  useMapLabelWheel(labelLayer, flat);
  const onCamera = useCallback((value: typeof camera) => {
    navigationCamera.current = value;
    setCamera((previous) => {
      const threshold = Math.max(2, value.distance * 0.005);
      return Math.hypot(
        previous.center[0] - value.center[0],
        previous.center[1] - value.center[1]
      ) < threshold &&
        Math.abs(previous.distance - value.distance) < threshold &&
        (previous.heightM ?? 0) === (value.heightM ?? 0)
        ? previous
        : value;
    });
  }, []);
  const unavailable = useCallback(() => {
    setFailed(true);
    setFlat(true);
  }, []);
  const chooseSite = useCallback(
    (value: SharedSite) => {
      setInfrastructureOpen(false);
      setFacilityExpansionOpen(false);
      setSelectedAssetId('');
      selectionRequest.current++;
      setSelected(value.districtId);
      const target = siteFocus(
        value,
        stage.current?.clientWidth ?? 800,
        stage.current?.clientHeight ?? 600
      );
      navigationCamera.current = target;
      setCamera(target);
      setSite(value);
      setType(value.allowedTypes.includes(type as FacilityType) ? type : value.allowedTypes[0]);
      setArea(String(Math.min(20, value.maxAreaM2)));
      setFeedback('');
      setListOpen(false);
      setOffset(0);
      setFocus((p) => ({
        ...target,
        key: p.key + 1,
      }));
    },
    [type]
  );
  const selectSite = useCallback(
    async (key: string) => {
      const request = ++selectionRequest.current;
      const found =
        shared.sites.find((s) => siteKey(s) === key) ??
        (site && siteKey(site) === key ? site : null);
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
    },
    [shared.sites, site, chooseSite]
  );
  const selectBuilding = useCallback(
    async (districtId: string, building: CityBuilding) => {
      setInfrastructureOpen(false);
      setFacilityExpansionOpen(false);
      setSelectedAssetId('');
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
    },
    [chooseSite]
  );
  const select = useCallback(
    (id: string) => {
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
    },
    [city, regions]
  );
  const reset = useCallback(() => {
    setSelected('');
    setCamera({ center: [0, 0], distance: 35000 });
    setSite(null);
    setOffset(0);
    selectionRequest.current++;
    setFocus((p) => ({ center: [0, 0], distance: 35000, key: p.key + 1, overview: true }));
  }, []);
  const district = city.districts.find((d) => d.id === selected);
  const ownDistrict = city.districts.find((d) => d.id === ownDistrictId);
  const preview = useMemo(
    () =>
      site &&
      !site.existingInfrastructure &&
      !occupied &&
      type &&
      Number(area) > 0 &&
      Number(area) <= site.maxAreaM2
        ? { site, placement: { cellId: site.cellId, facilityType: type, areaM2: Number(area) } }
        : null,
    [site, occupied, type, area]
  );
  const districtScores = useMemo(
    () =>
      researchMode
        ? null
        : new Map(
            city.districts.map((d) => {
              const score = weekly.value?.current.districts.find((v) => v.districtId === d.id);
              return [
                d.id,
                weekly.error
                  ? '순위 갱신 지연'
                  : score?.rank
                    ? `${score.rank}위 · ${scoreFormat.format(score.scoreM3)}m³`
                    : '평가 대기',
              ];
            })
          ),
    [city, researchMode, weekly.value, weekly.error]
  );
  const plan = (
    <CityPlan
      surfaceFrame={surface.frame}
      surfaceMetric={surfaceMetric}
      traceTiles={traces.tiles}
      publicAssets={publicAssets}
      selectedAssetId={selectedAssetId}
      onAsset={selectAsset}
      city={city}
      focus={focus}
      regions={regions}
      tiles={details.tiles}
      selected={selected}
      ownDistrictId={ownDistrictId ?? null}
      viewerId={viewerId ?? null}
      sites={visibleSites}
      installations={shared.installations}
      installationBySite={installationBySite}
      selectedSite={selectedSite}
      facilityType={type}
      eligibleRoofs={eligibility.roofIds}
      occupiedRoofs={occupiedRoofs}
      wetDistricts={wetDistricts}
      animateRain={animateRain}
      districtScores={districtScores}
      onDistrict={select}
      onSite={selectSite}
      onBuilding={selectBuilding}
      onCamera={onCamera}
      onNavigate={onNavigate}
      camera={camera}
      rainAmounts={rainAmounts}
    />
  );

  return (
    <main className="studio-layout play-layout shared-play-layout">
      <header className="play-hud">
        <div className="play-objective">
          <span>WATER LEAGUE / {researchMode ? '재해 모드' : '주간 서울 대항전'}</span>
          <h1>
            {researchMode
              ? `${research.event?.eventDate.replaceAll('-', '. ') ?? ''} 집중호우`
              : '주간 서울 대항전'}
            {district && <small className="game-district-name"> · {district.name}</small>}
          </h1>
          <small>
            {researchMode
              ? '서울 전역의 공개 후보에 설계하고, 관측 강우로 비교하세요.'
              : '빈 위치를 찾아 설치하고, 우리 구의 빗물을 줄여보세요.'}
          </small>
        </div>
        <div className="play-resources">
          {researchMode ? (
            <GameClock at={research.at ?? undefined} label="KST · 재해 재생" />
          ) : (
            <GameClock />
          )}
          {researchMode && (
            <button className="disaster-back" onClick={onExit}>
              <ArrowLeft size={15} />
              재난 다시 선택
            </button>
          )}
          <span>
            {researchMode ? '내 재해 설계 잔액' : account ? '내 설치 예산 잔액' : '1인당 설치 예산'}
            <b>{budget.value ? won(remaining) : '조회 중'}</b>
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
            <button
              aria-expanded={infrastructureOpen}
              onClick={() => {
                setInfrastructureOpen((value) => !value);
                setFacilityExpansionOpen(false);
              }}
            >
              <Layers3 size={15} />
              공개 시설
            </button>
            {!researchMode && (
              <button aria-expanded={rankingOpen} onClick={() => setRankingOpen((v) => !v)}>
                <Trophy size={15} />
                주간 순위
              </button>
            )}
          </div>
        </div>
        <FloodTraceControls
          enabled={tracesEnabled}
          onEnabled={(value) => {
            setTracesEnabled(value);
            setTraceRenderError(false);
          }}
          eventId={traceEventId}
          onEvent={setReferenceTraceEvent}
          fixedEvent={researchMode}
          catalog={traces.catalog}
          event={traces.event}
          loading={traces.loading}
          error={traces.error}
          renderError={traceRenderError}
          retry={traces.retry}
        />
        <section ref={stage} className="city-stage" aria-label="서울 전역 3D 지도">
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
                  surfaceFrame={surface.frame}
                  surfaceMetric={surfaceMetric}
                  onSurfaceError={surfaceFailed}
                  traceTiles={traces.tiles}
                  onTraceError={traceFailed}
                  publicAssets={publicAssets}
                  selectedAssetId={selectedAssetId}
                  onAsset={selectAsset}
                  terrain={terrain}
                  facilityType={type}
                  viewerId={viewerId ?? null}
                  city={city}
                  eligibleRoofs={eligibility.roofIds}
                  occupiedRoofs={occupiedRoofs}
                  regions={regions}
                  tiles={details.tiles}
                  focus={focus}
                  selected={selected}
                  onCamera={onCamera}
                  labels={labels.current}
                  onUnavailable={unavailable}
                  ownDistrictId={ownDistrictId ?? null}
                  sites={visibleSites}
                  installations={shared.installations}
                  installationBySite={installationBySite}
                  selectedSite={selectedSite}
                  onSite={selectSite}
                  onBuilding={selectBuilding}
                  wetDistricts={wetDistricts}
                  rainAmounts={rainAmounts}
                  rainCamera={camera}
                  animateRain={animateRain}
                  preview={preview}
                />
              </Suspense>
            </ErrorBoundary>
          )}
          {!flat && (
            <div ref={labelLayer} className="city-map-labels" aria-label="지도에서 자치구 선택">
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
                  if (flat)
                    setFocus((p) => ({
                      center: navigationCamera.current.center,
                      distance: navigationCamera.current.distance,
                      heightM: navigationCamera.current.heightM,
                      key: p.key + 1,
                    }));
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
                      second: '2-digit',
                      hourCycle: 'h23',
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
            {assetsEnabled && (
              <span>
                <i className="infrastructure-legend" />
                {researchMode ? '공개 시설 참고 · 당시 시설 아님' : '공개 시설 참고'}
              </span>
            )}
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
                      const installed = installationBySite.get(siteKey(s));
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
                            {installed
                              ? installed.ownerName + ' · 설치됨'
                              : s.existingInfrastructure
                                ? '공개 저류 영역 · 신규 설치 제외'
                                : '빈 위치'}{' '}
                            · 최대 {s.maxAreaM2.toLocaleString('ko-KR')} m²
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
          <div className="facility-dock facility-install-dock">
            <button
              className={facilityExpansionOpen ? 'selected' : ''}
              aria-expanded={facilityExpansionOpen}
              aria-controls="facility-install-panel"
              onClick={() => {
                setFacilityExpansionOpen((value) => !value);
                setInfrastructureOpen(false);
                setListOpen(false);
              }}
            >
              <Layers3 size={20} />
              <span>시설 설치하기</span>
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
        <SurfaceControls
          enabled={surfaceEnabled}
          onEnabled={setSurfaceEnabled}
          metric={surfaceMetric}
          onMetric={setSurfaceMetric}
          state={surface}
          hasSource={!!surfaceSource}
          onSeek={seekSurface}
          renderError={surfaceRenderError}
        />
        <details className="shared-rain-details">
          <summary>
            <CloudRain size={15} />
            {researchMode ? '재해 강우 · 재생 조절' : '실시간 강우 · 관측 정보 보기'}
          </summary>
          {researchMode ? (
            <HistoricalTimeline state={research} />
          ) : (
            <LiveRainfallPanel districtId={selected} rainfall={rainfall} />
          )}
        </details>
      </div>
      <FacilityExpansionPanel
        key={account ? `${account.id}:${account.role}:${account.approvalStatus}` : 'visitor'}
        account={account}
        open={facilityExpansionOpen}
        selectedMapFacility={type}
        onAllCandidates={() => {
          setType('');
          setOffset(0);
          setFacilityExpansionOpen(false);
        }}
        onClose={() => setFacilityExpansionOpen(false)}
        onLogin={onLogin}
        onMapFacility={(t) => {
          setFacilityExpansionOpen(false);
          setInfrastructureOpen(false);
          setSelectedAssetId('');
          setType(t);
          setOffset(0);
          setSite(null);
          setFeedback('');
          if (ownDistrictId && selected !== ownDistrictId) select(ownDistrictId);
          setListOpen(true);
        }}
      />
      {facilityExpansionOpen ? null : infrastructureOpen ? (
        <InfrastructurePanel
          catalog={infrastructure.catalog}
          error={infrastructure.error}
          retry={infrastructure.retry}
          selectedId={selectedAssetId}
          onSelect={selectAsset}
          onClose={() => setInfrastructureOpen(false)}
          districtId={selected}
          historical={researchMode}
          eventId={researchMode ? eventId : ''}
          enabled={assetsEnabled}
          onToggle={() => setAssetsEnabled((value) => !value)}
        />
      ) : researchMode ? (
        <HistoricalPanel
          state={research}
          districtName={district?.name ?? ''}
          site={site}
          type={type}
          area={area}
          onType={setType}
          onArea={setArea}
          onLogin={onLogin}
          authenticated={!!account}
          error={selectionError || budget.error}
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
          budget={budget.value}
          budgetReady={!!budget.value && !budget.error}
          busy={shared.busy}
          error={shared.error || selectionError || budget.error}
          feedback={feedback}
          onInstall={async (s, t, a) => {
            const ok = await shared.install(s, t, a);
            setBudgetRevision((v) => v + 1);
            if (ok) setFeedback('설치 완료 · 모두의 지도에 반영됐습니다');
            return ok;
          }}
          onRemove={async (id) => {
            const ok = await shared.remove(id);
            setBudgetRevision((v) => v + 1);
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
      {!researchMode && rankingOpen && (
        <section className="weekly-drawer" aria-label="주간 순위 패널">
          <button
            className="weekly-drawer-close"
            aria-label="주간 순위 닫기"
            onClick={() => setRankingOpen(false)}
          >
            <X size={18} />
          </button>
          <WeeklyBoard
            value={weekly.value}
            error={weekly.error}
            ownDistrictId={ownDistrictId ?? null}
            onDistrict={(id) => {
              select(id);
              setRankingOpen(false);
            }}
          />
        </section>
      )}
      <footer className="city-source-note">
        공개 형상 {city.sourceDate} ·{' '}
        {terrain
          ? 'Copernicus 공개 지표면 높이 · 90m 표시 격자'
          : terrainError
            ? '높이 자료 연결 실패 · 평면 표시'
            : '지표면 높이 연결 중'}{' '}
        · 건물 높이 태그·층수 환산 포함 ·{' '}
        {surface.frame
          ? '계산 침수는 별도 색상 레이어 · 표시 지형과 물리 기준고 구분'
          : '침수 깊이 표시 아님'}
        {assetsEnabled &&
          ' · 시설 위치: 서울특별시·강서구 / 공공누리 제1유형 · 저류 경계: OpenStreetMap / ODbL 1.0'}
        {terrain && (
          <>
            {' '}
            ·{' '}
            <a href="/data/seoul-terrain-v1/attribution.txt" target="_blank" rel="noreferrer">
              지표면 출처·이용조건
            </a>
          </>
        )}
      </footer>
    </main>
  );
}
export function CityExplorer({
  account,
  onLogin,
  onAccount,
  mode = 'shared',
  eventId,
  onExit,
  initialDistrictId,
}: PlayProps) {
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
      initialDistrictId={initialDistrictId}
      eventId={eventId}
      onExit={onExit}
      city={city}
      eligibility={eligibility}
      regions={regions}
      account={account}
      onLogin={onLogin}
      onAccount={onAccount}
    />
  );
}
