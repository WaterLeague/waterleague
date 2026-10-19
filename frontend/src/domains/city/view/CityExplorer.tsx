import { mapCursors } from '../service/mapCursor';
import { infrastructureFocus } from '../../infrastructure/service/infrastructureFocus';
import { GameSelect } from '../../../shared/ui/GameSelect';
import { MapActionDock } from './MapActionDock';
import { useGroundCandidates } from '../../installation/controller/useGroundCandidates';
import { GameplayScoreboard } from './GameplayScoreboard';
import { historicalTotal } from '../../historical/service/historicalTotal';
import { HistoricalWeatherBadge } from '../../historical/view/HistoricalWeatherBadge';
import { WeatherBadge } from '../../rainfall/view/WeatherBadge';
import { usePublicSurfaces } from '../../surface/controller/usePublicSurfaces';
import { PublicSurfaceControls } from '../../surface/view/PublicSurfaceControls';
import { placementAreaLimit } from '../../installation/service/placementAreaLimit';
import { lazy, Suspense, useEffect, useCallback, useState, useRef, useMemo } from 'react';
import { useUrbanTime } from '../../urban/controller/useUrbanTime';
import { emptyFloodStats, type FloodStats } from '../../urban/service/floodMovementService';
import { useLiveUrban } from '../../urban/controller/useLiveUrban';
import { LiveUrbanSource } from '../../urban/view/LiveUrbanSource';
import { useUrbanData } from '../../urban/controller/useUrbanData';
import {
  RotateCcw,
  CircleHelp,
  Plus,
  Minus,
  MapPin,
  Layers3,
  CloudRain,
  Grid2X2,
  House,
  List,
  X,
  Trophy,
  ArrowLeft,
} from 'lucide-react';
import { useCity, useCityTiles } from '../controller/useCity';
import { useMapLabelWheel } from '../controller/useMapLabelWheel';
import type { City, CityFocus, CityBuilding } from '../entity/city';
import type { CityEligibility } from '../dto/cityEligibilityDto';
import { representativeInstallations } from '../../installation/service/memberSitesService';
import { useInstallationLayout } from '../../installation/controller/useInstallationLayout';
import { occupiedRoofSource } from '../service/siteVisibilityService';
import { siteFocus, selectionView } from '../service/siteFocusService';
import { zoomPlanView, type PlanView } from '../service/planNavigationService';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { CityPlan } from './CityPlan';
import type { Account } from '../../account/entity/account';
import { useInstallations } from '../../installation/controller/useInstallations';
import { SharedDistrictPanel } from '../../installation/view/SharedDistrictPanel';
import type { SharedSite } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities } from '../../game/service/gameService';
import { viewingDistrict } from '../service/viewingDistrictService';
import {
  loadSite,
  loadBuildingSite,
  loadStreetSite,
  loadParkingSite,
} from '../../installation/repository/installationRepository';
import { ApiError, errorMessage } from '../../../shared/exception/ApiError';
import './shared-play.css';
import { siteKey } from '../../installation/entity/installation';
import '../../rainfall/view/rainfall.css';
import { useHistorical } from '../../historical/controller/useHistorical';
import { HistoricalPanel, HistoricalTimeline } from '../../historical/view/HistoricalPanel';
import { useLiveRainfall } from '../../rainfall/controller/useLiveRainfall';
import { isRaining } from '../../rainfall/service/rainEffectService';
import { useReducedMotion } from '../../catalog/controller/useReducedMotion';
import { useBudget } from '../../budget/controller/useBudget';
import { useWeekly } from '../../weekly/controller/useWeekly';
import { WeeklyBoard, scoreFormat } from '../../weekly/view/WeeklyBoard';
import { useTerrain } from '../../terrain/controller/useTerrain';
import { GameClock } from '../../game/view/GameClock';
import { useInfrastructure } from '../../infrastructure/controller/useInfrastructure';
import { useVisibleInfrastructure } from '../../infrastructure/controller/useVisibleInfrastructure';
import { unreservedRoofIds } from '../../infrastructure/service/infrastructureService';
import { InfrastructurePanel } from '../../infrastructure/view/InfrastructurePanel';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { useFloodTraces } from '../../floodtrace/controller/useFloodTraces';
import { FloodTraceControls } from '../../floodtrace/view/FloodTraceControls';
import { useSurfacePlayback } from '../../surface/controller/useSurfacePlayback';
import { SurfaceControls } from '../../surface/view/SurfaceControls';
import type { SurfaceMetric, SurfaceSource } from '../../surface/entity/surface';
import { FacilityExpansionPanel } from '../../watershed/view/FacilityExpansionPanel';
import { useCisternPlans } from '../../installation/controller/useCisternPlans';
import { CisternPlanPanel } from '../../installation/view/CisternPlanPanel';
import type { CisternSiteRole } from '../../installation/service/cisternPlanService';
import { observedWind, waterWeather } from '../../surface/service/waterAppearanceService';
import { useArchivedWaterWeather } from '../../rainfall/controller/useArchivedWaterWeather';
import { archivedWindAt } from '../../rainfall/service/archivedWeatherService';
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
  const [floodStats, setFloodStats] = useState<FloodStats>(emptyFloodStats);
  const onFloodStats = useCallback(
    (value: FloodStats) =>
      setFloodStats((previous) =>
        JSON.stringify(previous) === JSON.stringify(value) ? previous : value
      ),
    []
  );
  const { terrain, error: terrainError } = useTerrain();
  const infrastructure = useInfrastructure();
  const [infrastructureOpen, setInfrastructureOpen] = useState(false);
  const [facilityExpansionOpen, setFacilityExpansionOpen] = useState(false);
  const [cisternOpen, setCisternOpen] = useState(false);
  const cistern = useCisternPlans(account, cisternOpen);
  const [assetsEnabled, setAssetsEnabled] = useState(true);
  const [comparisonEventId, setComparisonEventId] = useState('');
  const surfaceEnabled = true;
  const [surfaceMetric, setSurfaceMetric] = useState<SurfaceMetric>('depth');
  const [surfaceIndex, setSurfaceIndex] = useState<number | null>(null);
  const [surfaceRenderError, setSurfaceRenderError] = useState(false);
  const surfaceFailed = useCallback(() => setSurfaceRenderError(true), []);
  const [traceRenderError, setTraceRenderError] = useState(false);
  const traceFailed = useCallback(() => setTraceRenderError(true), []);
  const [selectedAssetId, setSelectedAssetId] = useState('');
  const [budgetRevision, setBudgetRevision] = useState(0);
  const budget = useBudget(budgetRevision, account?.id ?? null);
  const weekly = useWeekly(!researchMode, account?.id ?? null);
  const districtScore = (id: string) => {
    if (weekly.error) return '순위 갱신 지연';
    const score = weekly.value?.current.districts.find((d) => d.districtId === id);
    return score
      ? `${score.rank ? `${score.rank}위 · ` : ''}총 점수 ${scoreFormat.format(score.scoreM3)} m³`
      : '점수 조회 중';
  };
  const [selected, setSelected] = useState(initialDistrictId);
  const [camera, setCamera] = useState<PlanView>({
    center: [0, 0],
    distance: 35000,
  });
  const navigationCamera = useRef(camera);
  const viewedDistrict = useMemo(
    () => (camera.distance >= 20000 ? undefined : viewingDistrict(city.districts, camera.center)),
    [city.districts, camera.center, camera.distance]
  );
  const viewedDistrictId = viewedDistrict?.id ?? '';
  const research = useHistorical(researchMode, selected, account, budget.value, eventId);
  const urbanClock = useUrbanTime(
    researchMode,
    research.at,
    research.playing,
    research.speed,
    research.event?.regions[0]?.start
  );
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
  const animateRain = rainfall.visible && !reducedMotion && (!researchMode || research.playing);
  const archivedWeather = useArchivedWaterWeather(researchMode, eventId);
  const archivedWind = archivedWindAt(archivedWeather, eventId, research.at, viewedDistrictId);
  const waterAppearance = useMemo(
    () =>
      researchMode
        ? {
            wind: observedWind(archivedWind?.windSpeedMs, archivedWind?.windDirectionDeg),
            rain:
              research.event?.regions.find((r) => r.districtId === viewedDistrictId)?.depthsMm[
                research.index
              ] ?? 0,
            windSpeed: archivedWind?.windSpeedMs ?? undefined,
          }
        : waterWeather(rainfall.value, viewedDistrictId, rainfall.now),
    [
      researchMode,
      research.event,
      research.index,
      rainfall.value,
      viewedDistrictId,
      rainfall.now,
      archivedWind?.windSpeedMs,
      archivedWind?.windDirectionDeg,
    ]
  );
  const [site, setSite] = useState<SharedSite | null>(null);
  const selectedSite = site?.cellId ?? '';
  const [type, setType] = useState<FacilityType | ''>('');
  const [siteSurface, setSiteSurface] = useState<'' | 'ROADWAY' | 'WALKWAY' | 'OTHER'>('');
  const mapFacilityType = cisternOpen
    ? cistern.role === 'roof'
      ? 'GREEN_ROOF'
      : 'PERMEABLE_PAVEMENT'
    : type;
  const planningRoles = useMemo(
    () =>
      new Map<string, CisternSiteRole>(
        cisternOpen
          ? (
              [
                ['roof', cistern.roof],
                ['ground', cistern.ground],
              ] as const
            ).flatMap(([role, value]) => (value ? [[siteKey(value), role]] : []))
          : []
      ),
    [cisternOpen, cistern.roof, cistern.ground]
  );
  const [area, setArea] = useState('20');
  const [listOpen, setListOpen] = useState(false);
  const listOpenRef = useRef(listOpen);
  useEffect(() => {
    listOpenRef.current = listOpen;
  }, [listOpen]);
  const [vacant, setVacant] = useState(false);
  const [offset, setOffset] = useState(0);
  const [feedback, setFeedback] = useState('');
  const [selectionError, setSelectionError] = useState('');
  const selectionRequest = useRef(0);
  useEffect(() => {
    // 선택 단계가 바뀐 뒤 도착한 이전 위치 조회가 새 계획을 덮어쓰지 않게 한다.
    selectionRequest.current++;
  }, [cisternOpen, cistern.role, account?.id, account?.districtId, mapFacilityType]);
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
  const workspace = useRef<HTMLElement>(null);
  const controlsBar = useRef<HTMLDivElement>(null);
  const legendMenu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      const menu = legendMenu.current;
      if (menu?.open && !menu.contains(event.target as Node)) menu.open = false;
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      const menu = legendMenu.current;
      if (event.key === 'Escape' && menu?.open) {
        menu.open = false;
        menu.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);
  useEffect(() => {
    if (!workspace.current || !controlsBar.current) return;
    const observer = new ResizeObserver(([entry]) =>
      workspace.current?.style.setProperty('--map-controls-height', `${entry.contentRect.height}px`)
    );
    observer.observe(controlsBar.current);
    return () => observer.disconnect();
  }, []);
  const urban = useUrbanData(camera.center, camera.distance);
  const groundCandidates = useGroundCandidates(camera.center, camera.distance);
  const liveUrban = useLiveUrban(camera.center, camera.distance, researchMode);
  const traces = useFloodTraces(true, researchMode ? eventId : comparisonEventId, camera);
  const eligibleRoofs = useMemo(
    () => unreservedRoofIds(eligibility.roofIds, infrastructure.catalog?.assets ?? null),
    [eligibility.roofIds, infrastructure.catalog]
  );
  const publicAssets = useVisibleInfrastructure(
    infrastructure.catalog?.assets,
    assetsEnabled,
    camera.center,
    camera.distance,
    selectedAssetId
  );
  const selectAsset = useCallback((asset: InfrastructureAsset) => {
    setCisternOpen(false);
    setType('');
    selectionRequest.current++;
    setSite(null);
    setSelectionError('');
    setFeedback('');
    setSelected(asset.districtId);
    setSelectedAssetId(asset.id);
    setInfrastructureOpen(true);
    setFacilityExpansionOpen(false);
    setAssetsEnabled(true);
    const current = navigationCamera.current;
    const target = infrastructureFocus(
      asset,
      stage.current?.clientWidth ?? 800,
      stage.current?.clientHeight ?? 600,
      current
    );
    navigationCamera.current = target;
    setCamera(target);
    if (target !== current) setFocus((previous) => ({ ...target, key: previous.key + 1 }));
  }, []);
  const onNavigate = useCallback((value: typeof camera) => {
    navigationCamera.current = value;
  }, []);
  const sharedData = useInstallations(
    {
      districtId: selected,
      x: Math.round(camera.center[0]),
      y: Math.round(camera.center[1]),
      offset,
      type: mapFacilityType,
      surface: cisternOpen ? 'OTHER' : mapFacilityType === 'PERMEABLE_PAVEMENT' ? siteSurface : '',
      vacant: researchMode ? false : vacant,
    },
    !researchMode || cisternOpen
  );
  const researchVisibleKey = research.drafts
    .filter((d) => research.at && Date.parse(d.marker.installedAt) <= Date.parse(research.at))
    .map((d) => d.marker.id)
    .join(',');
  const researchMarkers = useMemo(
    () =>
      research.drafts
        .filter((d) => researchVisibleKey.split(',').includes(d.marker.id))
        .map((d) => {
          const score = research.facilityStates.find(
            (state) => state.draft.marker.id === d.marker.id
          )?.score;
          return {
            ...d.marker,
            ownerId: viewerId!,
            scoreM3: score?.differenceM3 ?? null,
            evaluatedThrough: score?.at ?? null,
          };
        }),
    [research.drafts, researchVisibleKey, research.facilityStates, viewerId]
  );
  const shared = {
    ...sharedData,
    installations: researchMode && !cisternOpen ? researchMarkers : sharedData.installations,
  };
  const installationBySite = useMemo(
    () => representativeInstallations(shared.installations, viewerId ?? null),
    [shared.installations, viewerId]
  );
  const layout = useInstallationLayout(shared.installations, viewerId ?? null);
  const occupiedRoofs = useMemo(
    () =>
      new Set(
        layout.placements
          .filter((i) => i.ownerId === viewerId)
          .flatMap((i) => occupiedRoofSource(i.districtId, i.cellId, eligibility.legacySiteSources))
      ),
    [layout.placements, viewerId, eligibility]
  );
  const ownInstallations = shared.installations.filter((i) => i.ownerId === viewerId);
  const ownSiteKeys = useMemo(
    () => new Set(layout.placements.filter((i) => i.ownerId === viewerId).map(siteKey)),
    [layout.placements, viewerId]
  );
  const remaining = researchMode ? research.remaining : (budget.value?.remainingKrw ?? 0);
  const occupied = site ? ownInstallations.find((i) => siteKey(i) === siteKey(site)) : undefined;
  const publicSurface = usePublicSurfaces(!researchMode, camera, city);
  const surfaceSource: SurfaceSource | null = researchMode
    ? account && research.job?.state === 'SUCCEEDED' && research.currentResult
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
    researchMode ? null : surfaceIndex,
    researchMode ? null : rainfall.now
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
    const values = new Map(shared.mapSites.map((s) => [siteKey(s), s]));
    if (site) values.set(siteKey(site), site);
    if (cisternOpen)
      for (const value of [cistern.roof, cistern.ground])
        if (value) values.set(siteKey(value), value);
    return [...values.values()].filter(
      (s) =>
        s === site ||
        planningRoles.has(siteKey(s)) ||
        Math.hypot(s.center[0] - camera.center[0], s.center[1] - camera.center[1]) <
          camera.distance * 1.3
    );
  }, [shared.mapSites, site, camera, cisternOpen, cistern.roof, cistern.ground, planningRoles]);
  const closeInstallation = useCallback(() => {
    selectionRequest.current++;
    setFacilityExpansionOpen(false);
    setListOpen(false);
    setCisternOpen(false);
    setSite(null);
    setType('');
    setSiteSurface('');
    setOffset(0);
    setSelectionError('');
    setFeedback('');
  }, []);
  const details = useCityTiles(city, camera);
  const labels = useRef(new Map<string, HTMLElement>());
  const labelLayer = useRef<HTMLDivElement>(null);
  useMapLabelWheel(labelLayer, flat);
  const onCamera = useCallback((value: typeof camera) => {
    navigationCamera.current = value;
    setCamera((previous) => {
      const threshold = listOpenRef.current ? 1 : Math.max(2, value.distance * 0.005);
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
  useEffect(() => {
    if (!listOpen) return;
    setOffset(0);
    const viewed = viewingDistrict(city.districts, camera.center);
    if (viewed) setSelected(viewed.id);
  }, [listOpen, city.districts, camera.center[0], camera.center[1]]);
  const unavailable = useCallback(() => {
    setFailed(true);
    setFlat(true);
  }, []);
  const chooseSite = useCallback(
    (value: SharedSite, inspect = false, fromMap = false) => {
      const inspecting =
        inspect || (!cisternOpen && !mapFacilityType && installationBySite.has(siteKey(value)));
      if (
        !inspecting &&
        (!fromMap || cisternOpen) &&
        mapFacilityType &&
        (!value.allowedTypes.includes(mapFacilityType) ||
          value.existingInfrastructure ||
          ownSiteKeys.has(siteKey(value)) ||
          (ownDistrictId && value.districtId !== ownDistrictId))
      )
        return;
      if (
        cisternOpen &&
        (cistern.busy || !cistern.select(value, installationBySite.has(siteKey(value))))
      )
        return;
      setInfrastructureOpen(false);
      setFacilityExpansionOpen(false);
      setSelectedAssetId('');
      selectionRequest.current++;
      setSelected(value.districtId);
      const current = navigationCamera.current;
      const target = selectionView(
        siteFocus(value, stage.current?.clientWidth ?? 800, stage.current?.clientHeight ?? 600),
        current,
        fromMap
      );
      navigationCamera.current = target;
      setCamera(target);
      setSite(value);
      const chosen =
        cisternOpen || inspecting
          ? ''
          : value.allowedTypes.includes(type as FacilityType)
            ? type
            : value.allowedTypes[0];
      setType(chosen);
      setArea(String(Math.min(20, placementAreaLimit(value, chosen))));
      setFeedback('');
      setListOpen(cisternOpen && cistern.role === 'roof');
      setOffset(0);
      if (target !== current)
        setFocus((p) => ({
          ...target,
          key: p.key + 1,
          preserveAngle: target.distance === current.distance,
        }));
    },
    [
      type,
      cisternOpen,
      cistern.busy,
      cistern.select,
      cistern.role,
      installationBySite,
      mapFacilityType,
      ownDistrictId,
      ownSiteKeys,
    ]
  );
  const selectSite = useCallback(
    async (key: string) => {
      const request = ++selectionRequest.current;
      const found =
        visibleSites.find((s) => siteKey(s) === key) ??
        (site && siteKey(site) === key ? site : null);
      setSelectionError('');
      if (found) {
        chooseSite(found, ownSiteKeys.has(key), true);
        return;
      }
      const [districtId, cellId] = key.split(':');
      try {
        const value = await loadSite(districtId, cellId);
        if (request === selectionRequest.current) chooseSite(value, ownSiteKeys.has(key), true);
      } catch {
        if (request === selectionRequest.current)
          setSelectionError('위치 정보를 불러오지 못했습니다. 다시 선택해 주세요.');
      }
    },
    [visibleSites, site, chooseSite, ownSiteKeys]
  );
  const selectStreet = useCallback(
    async (sourceId: string, point: [number, number]) => {
      if (cisternOpen) return;
      const districtId = viewingDistrict(city.districts, point)?.id;
      if (!districtId) return;
      const request = ++selectionRequest.current;
      setSelectionError('');
      try {
        const value = await loadStreetSite(districtId, sourceId, point);
        if (request === selectionRequest.current) chooseSite(value, false, true);
      } catch (error) {
        if (request === selectionRequest.current) {
          setSite(null);
          setInfrastructureOpen(false);
          setFacilityExpansionOpen(false);
          setSelectionError(
            error instanceof ApiError && error.code === 'RESOURCE_NOT_FOUND'
              ? '이 구간에는 설치 가능한 투수포장 구역이 없습니다. 표시된 주변 후보를 선택해 주세요.'
              : '도로 위치를 불러오지 못했습니다. 다시 선택해 주세요.'
          );
        }
      }
    },
    [cisternOpen, city.districts, chooseSite]
  );
  const selectParking = useCallback(
    async (sourceId: string, point: [number, number]) => {
      const districtId = viewingDistrict(city.districts, point)?.id;
      if (!districtId) return;
      const request = ++selectionRequest.current;
      setSelected(districtId);
      setInfrastructureOpen(false);
      setFacilityExpansionOpen(false);
      setListOpen(false);
      setSelectionError('');
      try {
        const value = await loadParkingSite(districtId, sourceId, point);
        if (request === selectionRequest.current) chooseSite(value, false, true);
      } catch (error) {
        if (request === selectionRequest.current) {
          setSite(null);
          setSelectionError(
            error instanceof ApiError && error.code === 'RESOURCE_NOT_FOUND'
              ? '선택한 주차장 위치에는 공개자료로 확인된 설치 후보가 없습니다. 주변 주차 칸을 선택해 주세요.'
              : '주차장 위치를 불러오지 못했습니다. 다시 선택해 주세요.'
          );
        }
      }
    },
    [city.districts, chooseSite]
  );
  const selectBuilding = useCallback(
    async (districtId: string, building: CityBuilding) => {
      if (
        cisternOpen &&
        mapFacilityType &&
        (mapFacilityType !== 'GREEN_ROOF' ||
          !eligibleRoofs.has(building.id) ||
          occupiedRoofs.has(building.id) ||
          (ownDistrictId && districtId !== ownDistrictId))
      )
        return;
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
        if (request === selectionRequest.current) chooseSite(value, false, true);
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
    [chooseSite, cisternOpen, mapFacilityType, eligibleRoofs, ownDistrictId, occupiedRoofs]
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
  const locateCistern = (value: SharedSite) => {
    const current = navigationCamera.current;
    const target = selectionView(
      siteFocus(value, stage.current?.clientWidth ?? 800, stage.current?.clientHeight ?? 600),
      current
    );
    setSelected(value.districtId);
    setSite(value);
    setType('');
    setOffset(0);
    setListOpen(false);
    navigationCamera.current = target;
    setCamera(target);
    setFocus((p) => ({
      ...target,
      key: p.key + 1,
      preserveAngle: target.distance === current.distance,
    }));
  };
  const zoomMap = (factor: number) => {
    const current = navigationCamera.current;
    const target = zoomPlanView(current, current.center, factor);
    navigationCamera.current = target;
    setCamera(target);
    setFocus((p) => ({ ...target, key: p.key + 1, preserveAngle: true }));
  };
  const disasterTotal = historicalTotal(research, !!account);
  const district = city.districts.find((d) => d.id === selected);
  const ownDistrict = city.districts.find((d) => d.id === ownDistrictId);
  const planned =
    researchMode && !!site && research.drafts.some((d) => siteKey(d.site) === siteKey(site));
  const preview = useMemo(
    () =>
      !cisternOpen &&
      site &&
      !site.existingInfrastructure &&
      !occupied &&
      !planned &&
      type &&
      Number(area) > 0 &&
      Number(area) <= placementAreaLimit(site, type)
        ? { site, placement: { cellId: site.cellId, facilityType: type, areaM2: Number(area) } }
        : null,
    [site, occupied, planned, type, area, cisternOpen]
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
                  : `시설 ${shared.installations.filter((i) => i.districtId === d.id).length}개 · ${score ? `총 점수 ${scoreFormat.format(score.scoreM3)} m³` : '점수 조회 중'}`,
              ];
            })
          ),
    [city, researchMode, weekly.value, weekly.error, shared.installations]
  );
  const plan = (
    <CityPlan
      parking={urban.parking}
      streets={urban.roads}
      preview={preview}
      surfaceFrame={surface.frame}
      publicSurfaceFrames={publicSurface.frames}
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
      groundCandidates={groundCandidates.rows}
      occupiedSites={ownSiteKeys}
      installations={shared.installations}
      installationBySite={layout.bySite}
      selectedSite={selectedSite}
      facilityType={mapFacilityType}
      planningRoles={planningRoles}
      cisternGeometry={cisternOpen ? cistern.geometry : null}
      eligibleRoofs={eligibleRoofs}
      occupiedRoofs={occupiedRoofs}
      wetDistricts={wetDistricts}
      animateRain={animateRain}
      districtScores={districtScores}
      onDistrict={select}
      onSite={selectSite}
      onBuilding={selectBuilding}
      onStreet={selectStreet}
      onParking={selectParking}
      onCamera={onCamera}
      onNavigate={onNavigate}
      camera={camera}
      rainAmounts={rainAmounts}
    />
  );

  const floodTraceControls = (
    <FloodTraceControls
      eventId={researchMode ? eventId : comparisonEventId}
      onEvent={(value) => {
        setComparisonEventId(value);
        setTraceRenderError(false);
      }}
      fixedEvent={researchMode}
      catalog={traces.catalog}
      event={traces.event}
      loading={traces.loading}
      error={traces.error}
      renderError={traceRenderError}
      retry={traces.retry}
    />
  );
  const publicFacilityToggle = (
    <button
      type="button"
      className="public-facility-toggle"
      role="switch"
      aria-label="공개 시설 표시"
      aria-checked={assetsEnabled}
      onClick={() => {
        setAssetsEnabled(!assetsEnabled);
        if (assetsEnabled) {
          setInfrastructureOpen(false);
          setSelectedAssetId('');
        }
      }}
    >
      <span>공개 시설 표시</span>
      <span className="map-switch-track" aria-hidden="true">
        <span />
      </span>
    </button>
  );

  return (
    <main
      ref={workspace}
      style={
        {
          '--map-cursor-install': mapCursors.install,
          '--map-cursor-inspect': mapCursors.inspect,
        } as React.CSSProperties
      }
      className={`studio-layout play-layout shared-play-layout${researchMode ? ' historical-play-layout' : ''}${!facilityExpansionOpen && !cisternOpen && !infrastructureOpen && !site && !selectionError ? ' shared-map-only' : ''}`}
    >
      <header className="play-hud gameplay-hud">
        <div className="play-objective">
          {researchMode && (
            <button
              className="disaster-back"
              onClick={onExit}
              title="재난 다시 선택"
              aria-label="재난 다시 선택"
            >
              <ArrowLeft size={16} />
              <span>재난 다시 선택</span>
            </button>
          )}
          <h1>
            {researchMode
              ? `${research.event?.eventDate.replaceAll('-', '. ') ?? ''} 집중호우`
              : '주간 서울 대항전'}
          </h1>
        </div>
        <div className="play-resources">
          {researchMode ? (
            <HistoricalWeatherBadge
              state={research}
              districtId={viewedDistrictId}
              districtName={viewedDistrict?.name ?? ''}
            />
          ) : (
            <WeatherBadge
              value={rainfall.value}
              districtId={viewedDistrictId}
              now={rainfall.now}
              busy={rainfall.busy}
              retry={rainfall.refresh}
              error={rainfall.error}
            />
          )}
          <GameplayScoreboard
            historical={researchMode}
            authenticated={!!account}
            weekly={researchMode ? null : weekly.value}
            district={weekly.value?.current.districts.find(
              (d) => d.districtId === account?.districtId
            )}
            count={
              researchMode
                ? disasterTotal.count
                : account && shared.ready
                  ? ownInstallations.length
                  : null
            }
            score={
              researchMode
                ? disasterTotal.score
                : account && weekly.value
                  ? (weekly.value.current.own?.scoreM3 ??
                    (shared.ready && !ownInstallations.length ? 0 : null))
                  : null
            }
            locked={researchMode && disasterTotal.locked}
          />
        </div>
      </header>
      <div className="design-main shared-map-column">
        <div ref={controlsBar} className="map-layer-bar">
          <div className="shared-toolbar gameplay-toolbar">
            <label>
              <MapPin size={15} />
              <GameSelect
                label="서울 자치구 선택"
                value={viewedDistrictId}
                onChange={(id) => (id ? select(id) : reset())}
                options={[
                  { value: '', label: '서울 전체' },
                  ...city.districts.map((d) => ({
                    value: d.id,
                    label: d.name + (d.id === ownDistrictId ? ' · 내 소속 구' : ''),
                  })),
                ]}
              />
            </label>
            <details
              className="gameplay-tools"
              onClick={(event) => {
                if (event.target instanceof Element && event.target.closest('[data-close-tools]'))
                  event.currentTarget.open = false;
              }}
            >
              <summary>
                <Layers3 size={15} />
                지도 도구
              </summary>
              <div>
                {!researchMode && (
                  <button
                    data-close-tools
                    onClick={() => {
                      if (account?.districtId) select(account.districtId);
                      else onLogin();
                    }}
                  >
                    <MapPin size={14} />내 소속 구
                  </button>
                )}
                <button
                  data-close-tools
                  aria-expanded={listOpen}
                  onClick={() => {
                    setCamera(navigationCamera.current);
                    setListOpen((v) => !v);
                  }}
                >
                  <List size={15} />
                  위치 목록
                </button>
                <button
                  data-close-tools
                  aria-expanded={infrastructureOpen}
                  disabled={!assetsEnabled}
                  onClick={() => {
                    setInfrastructureOpen((value) => !value);
                    setFacilityExpansionOpen(false);
                  }}
                >
                  <Layers3 size={15} />
                  공개 시설
                </button>
                {!researchMode && (
                  <button
                    data-close-tools
                    aria-expanded={rankingOpen}
                    onClick={() => setRankingOpen((v) => !v)}
                  >
                    <Trophy size={15} />
                    주간 순위
                  </button>
                )}
                <div className="gameplay-map-options">
                  {publicFacilityToggle}
                  {floodTraceControls}
                </div>
              </div>
            </details>
          </div>
          {researchMode ? (
            <HistoricalTimeline
              districtId={viewedDistrictId}
              state={research}
              onInspect={(d) => chooseSite(d.site, true)}
            >
              <SurfaceControls
                metric={surfaceMetric}
                onMetric={setSurfaceMetric}
                state={surface}
                hasSource={!!surfaceSource}
                onSeek={seekSurface}
                renderError={surfaceRenderError}
              />
            </HistoricalTimeline>
          ) : (
            <GameClock />
          )}
        </div>
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
                  parking={urban.parking}
                  urbanClock={urbanClock}
                  streets={urban.roads}
                  population={urban.population}
                  livePlaces={liveUrban.places}
                  historical={researchMode}
                  onFloodStats={onFloodStats}
                  surfaceFrame={surface.frame}
                  publicSurfaceFrames={publicSurface.frames}
                  surfaceMetric={surfaceMetric}
                  onSurfaceError={surfaceFailed}
                  traceTiles={traces.tiles}
                  onTraceError={traceFailed}
                  publicAssets={publicAssets}
                  selectedAssetId={selectedAssetId}
                  onAsset={selectAsset}
                  terrain={terrain}
                  facilityType={mapFacilityType}
                  planningRoles={planningRoles}
                  cisternGeometry={cisternOpen ? cistern.geometry : null}
                  viewerId={viewerId ?? null}
                  city={city}
                  eligibleRoofs={eligibleRoofs}
                  occupiedRoofs={occupiedRoofs}
                  regions={regions}
                  tiles={details.tiles}
                  focus={focus}
                  selected={selected}
                  onCamera={onCamera}
                  onNavigate={onNavigate}
                  labels={labels.current}
                  onUnavailable={unavailable}
                  ownDistrictId={ownDistrictId ?? null}
                  sites={visibleSites}
                  groundCandidates={groundCandidates.rows}
                  occupiedSites={ownSiteKeys}
                  installations={shared.installations}
                  installationBySite={layout.bySite}
                  selectedSite={selectedSite}
                  onSite={selectSite}
                  onBuilding={selectBuilding}
                  onStreet={selectStreet}
                  onParking={selectParking}
                  wetDistricts={wetDistricts}
                  rainAmounts={rainAmounts}
                  rainCamera={camera}
                  animateRain={animateRain}
                  waterWeather={waterAppearance}
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
                      aria-label={researchMode ? '재해 당시 비 재생' : '최근 관측 비 감지'}
                    />
                  )}
                  <small>
                    시설 {shared.installations.filter((i) => i.districtId === d.id).length}개
                    {!researchMode && districtScore(d.id) && ` · ${districtScore(d.id)}`}
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
                  ● {r.districtName} · 시설{' '}
                  {shared.installations.filter((i) => i.districtId === r.districtId).length}개
                  {!researchMode &&
                    districtScore(r.districtId) &&
                    ` · ${districtScore(r.districtId)}`}
                </button>
              ))}
            </div>
          )}
          <div className="city-map-top">
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
              <button onClick={() => zoomMap(0.6)} aria-label="지도 확대" title="지도 확대">
                <Plus size={16} />
              </button>
              <button onClick={() => zoomMap(1 / 0.6)} aria-label="지도 축소" title="지도 축소">
                <Minus size={16} />
              </button>
              <button onClick={reset} aria-label="서울 전체 보기">
                <RotateCcw size={15} />
              </button>
              <details ref={legendMenu} className="map-legend-menu">
                <summary aria-label="지도 범례" title="지도 표시 안내">
                  <CircleHelp size={17} />
                </summary>
                <div className="shared-map-legend" role="region" aria-label="지도 표시 안내">
                  {!flat && !failed && Object.values(floodStats).some((value) => value > 0) && (
                    <span
                      className="flood-response-legend"
                      role="status"
                      aria-label="주변 침수 반응 · 표시 객체 수"
                      title="주변 표시 객체의 반응이며 실제 피해 통계가 아닙니다. 과거 침수흔적은 사건 전체 범위입니다."
                    >
                      <i className="flood-response-dot" />
                      {floodStats.stopped > 0 && `감속·정차 ${floodStats.stopped} `}
                      {floodStats.exposed > 0 && `침수 노출 ${floodStats.exposed} `}
                      {floodStats.avoiding > 0 && `회피·대피 ${floodStats.avoiding} `}
                      {floodStats.stranded > 0 && `고립 ${floodStats.stranded}`}
                      <small>표시 객체</small>
                    </span>
                  )}
                  <span>
                    <i className="player-facility-legend" />
                    사용자 시설
                  </span>
                  <span>
                    <i className="river-legend" />
                    강·하천
                  </span>
                  <span>
                    <i className="flood-legend" />
                    계산 침수 · 수심/유속 색상
                  </span>
                  {assetsEnabled && (
                    <span>
                      <i className="infrastructure-legend" />
                      {researchMode ? '공개 시설 참고 · 당시 시설 아님' : '공개 시설 참고'}
                    </span>
                  )}
                  <span>
                    <i className="available" />
                    설치 가능
                  </span>
                  <span>
                    <i className="selected-site" />
                    선택 구역
                  </span>
                  {mapFacilityType && (
                    <span>
                      <i className="unavailable" />
                      {researchMode
                        ? '선택 시설 설치 불가'
                        : type
                          ? '선택 시설 설치 불가·내 설치'
                          : '후보 제외·내 설치'}
                    </span>
                  )}
                  {ownDistrict && (
                    <span>
                      <i className="other" />
                      다른 구 · 조회만
                    </span>
                  )}
                </div>
              </details>
            </div>
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
                <button aria-label="위치 목록 닫기" onClick={closeInstallation}>
                  <X size={16} />
                </button>
              </div>
              {!cisternOpen && (
                <label className="location-type-filter">
                  <select
                    aria-label="설치 위치 시설 종류"
                    value={type}
                    onChange={(e) => {
                      setType(e.target.value as FacilityType | '');
                      setOffset(0);
                    }}
                  >
                    <option value="">모든 시설</option>
                    {(Object.keys(facilities) as FacilityType[]).map((value) => (
                      <option key={value} value={value}>
                        {facilities[value].name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {!cisternOpen && type === 'PERMEABLE_PAVEMENT' && (
                <label className="location-type-filter">
                  <select
                    aria-label="투수포장 설치 지면"
                    value={siteSurface}
                    onChange={(event) => {
                      setSiteSurface(event.target.value as typeof siteSurface);
                      setOffset(0);
                    }}
                  >
                    <option value="">모든 지면</option>
                    <option value="ROADWAY">차도</option>
                    <option value="WALKWAY">인도·보행로</option>
                    <option value="OTHER">주차장·기타 지상</option>
                  </select>
                </label>
              )}
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
                  공개 시설 영역 제외
                </label>
              )}
              {!selected ? (
                <p>먼저 구를 선택해 주세요.</p>
              ) : shared.siteBusy && !shared.sites.length ? (
                <p role="status">지도 주변 후보 조회 중</p>
              ) : shared.siteError ? (
                <p role="alert">
                  {shared.siteError}
                  <button onClick={shared.retrySites}>다시 조회</button>
                </p>
              ) : (
                <>
                  <p>
                    {shared.matchedCount.toLocaleString('ko-KR')}곳 · 현재 보는 위치에서 가까운 순
                  </p>
                  <div className="shared-location-items" aria-busy={shared.siteBusy}>
                    {shared.sites
                      .filter(
                        (s) =>
                          !mapFacilityType ||
                          (!s.existingInfrastructure &&
                            !ownSiteKeys.has(siteKey(s)) &&
                            (!ownDistrictId || s.districtId === ownDistrictId))
                      )
                      .map((s) => {
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
                              {Math.round(
                                Math.hypot(
                                  s.center[0] - camera.center[0],
                                  s.center[1] - camera.center[1]
                                )
                              ).toLocaleString('ko-KR')}{' '}
                              m ·{' '}
                              {installed
                                ? installed.ownerId === viewerId
                                  ? '내 시설 · 시즌 고정'
                                  : installed.ownerName + ' · 같은 위치 설치 가능'
                                : s.existingInfrastructure
                                  ? '공개 시설 영역 · 신규 설치 제외'
                                  : '빈 위치'}{' '}
                              · 최대 {placementAreaLimit(s, type).toLocaleString('ko-KR')} m²
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
          {shared.siteError && (
            <div className="shared-map-count" role="alert">
              <span>설치 후보 조회 실패</span>
              <button onClick={shared.retrySites}>다시 조회</button>
            </div>
          )}
          <MapActionDock
            historical={researchMode}
            research={research}
            account={account}
            budget={budget.value}
            remaining={remaining}
            ownInstallations={ownInstallations}
            districts={city.districts}
            onLogin={onLogin}
            onHistoricalInspect={(d) => {
              const start = research.event?.regions[0].start;
              if (start)
                research.setElapsedSeconds(
                  (Date.parse(d.marker.installedAt) - Date.parse(start)) / 1000
                );
              research.setPlaying(false);
              chooseSite(d.site, true);
            }}
            onInspect={(value) => {
              const request = ++selectionRequest.current;
              void loadSite(value.districtId, value.cellId)
                .then((s) => {
                  if (request === selectionRequest.current) chooseSite(s, true);
                })
                .catch((e) => {
                  if (request === selectionRequest.current) setSelectionError(errorMessage(e));
                });
            }}
          >
            <button
              className={facilityExpansionOpen ? 'selected' : ''}
              aria-expanded={facilityExpansionOpen}
              aria-controls="facility-install-panel"
              onClick={() => {
                setCisternOpen(false);
                if (facilityExpansionOpen || listOpen || site || type) {
                  closeInstallation();
                  return;
                }
                setFacilityExpansionOpen(true);
                setInfrastructureOpen(false);
                setListOpen(false);
              }}
            >
              <Layers3 size={20} />
              <span>시설 설치하기</span>
            </button>
          </MapActionDock>
          {(details.error || failed) && (
            <p className="city-error" role="alert">
              {failed ? '3D 연결이 끊겨 2D 지도로 전환했습니다.' : details.error}
            </p>
          )}
          <a className="city-credit" href={city.licenseUrl} target="_blank" rel="noreferrer">
            {city.attribution}
          </a>
        </section>
        {!researchMode &&
          (!surface.frame ? (
            <PublicSurfaceControls
              state={publicSurface}
              metric={surfaceMetric}
              onMetric={setSurfaceMetric}
              renderError={surfaceRenderError}
            />
          ) : (
            <SurfaceControls
              live={!researchMode}
              metric={surfaceMetric}
              onMetric={setSurfaceMetric}
              state={surface}
              hasSource={!!surfaceSource}
              onSeek={seekSurface}
              renderError={surfaceRenderError}
            />
          ))}
      </div>
      <FacilityExpansionPanel
        key={account ? `${account.id}:${account.role}:${account.approvalStatus}` : 'visitor'}
        account={account}
        open={facilityExpansionOpen}
        budget={
          researchMode && research.budget && research.accounting
            ? {
                ...research.budget,
                accounting: research.accounting,
                remainingKrw: research.remaining,
                allocatedKrw: research.budget.policy.personalLimitKrw - research.remaining,
              }
            : budget.value
        }
        selectedMapFacility={type}
        onClose={closeInstallation}
        onLogin={onLogin}
        onCisternPlan={() => {
          setCisternOpen(true);
          setFacilityExpansionOpen(false);
          setInfrastructureOpen(false);
          setSelectedAssetId('');
          setType('');
          setSite(null);
          setOffset(0);
          setListOpen(true);
          if (account?.districtId && selected !== account.districtId) select(account.districtId);
        }}
        onMapFacility={(t) => {
          setCisternOpen(false);
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
      {facilityExpansionOpen ? null : cisternOpen ? (
        <CisternPlanPanel
          state={cistern}
          onClose={closeInstallation}
          onLogin={onLogin}
          onLocate={locateCistern}
          onChoose={(role) => {
            cistern.setRole(role);
            setSite(null);
            setOffset(0);
            setListOpen(true);
          }}
        />
      ) : infrastructureOpen ? (
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
        />
      ) : researchMode ? (
        <HistoricalPanel
          onClose={closeInstallation}
          state={research}
          districtName={district?.name ?? ''}
          site={site}
          type={type}
          area={area}
          onType={(next) => {
            setType(next);
            if (site) setArea(String(Math.min(Number(area) || 20, placementAreaLimit(site, next))));
          }}
          onArea={setArea}
          authenticated={!!account}
          error={selectionError || budget.error}
        />
      ) : (
        <SharedDistrictPanel
          onClose={closeInstallation}
          account={account}
          districtId={selected}
          districtName={district?.name ?? ''}
          site={site}
          occupied={occupied}
          type={type}
          area={area}
          onType={(next) => {
            setType(next);
            if (site) setArea(String(Math.min(Number(area) || 20, placementAreaLimit(site, next))));
          }}
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
            if (ok) setFeedback('설치 확정 · 이번 시즌 종료까지 유지됩니다');
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
        <details>
          <summary>지도 자료·표시 범위</summary>
          공개 형상 {city.sourceDate} ·{' '}
          {terrain
            ? 'Copernicus 공개 지표면 높이 · 90m 표시 격자'
            : terrainError
              ? '높이 자료 연결 실패 · 평면 표시'
              : '지표면 높이 연결 중'}{' '}
          · 건물 높이 태그·층수 환산 포함 ·{' '}
          {surface.frame || publicSurface.frames.length
            ? '계산 침수는 원 수심의 상대 높이·색상 표시 · 실제 수면 표고 아님'
            : '침수 깊이 표시 아님'}
          {' · 물결은 기상 기반 시각 효과 · 하천 실측 유속 아님'}
          {' · 태양: 서울 좌표·재생 시각의 천문 계산 · 창문·가로등·차량·보행자: 게임 연출'}
          {researchMode
            ? eventId === 'seoul-20220808'
              ? ' · 인구 밀도: 2022-08-08~09 시간대별 생활인구(내국인)'
              : ' · 해당 사건의 시간대별 인구 미확보: 일반 교통·보행 연출'
            : ' · 인구 밀도: 서울시 공개 장소의 현재 인구 범위 · 장소 밖/자료 만료 시 2025 요일·시간대 참고값'}
          {!researchMode && (
            <LiveUrbanSource places={liveUrban.current} now={liveUrban.checkedAt} />
          )}
          {' · 도로 폭 결측·보도·교량 높이는 표시 가정 · 과거 도로망 복원 아님'}
          {' · 주차 칸·정차 차량 배치는 고정 게임 연출 · 실제 주차 점유율 아님'}
          {urban.error && ` · ${urban.error}`}
          {groundCandidates.error && ` · ${groundCandidates.error}`}
          {urban.populationError && ` · ${urban.populationError}`}
          {assetsEnabled &&
            ' · 시설 위치: 서울특별시·강서구 / 공공누리 제1유형 · 시설 경계: OpenStreetMap / ODbL 1.0'}
          {terrain && (
            <>
              {' '}
              ·{' '}
              <a href="/data/seoul-terrain-v1/attribution.txt" target="_blank" rel="noreferrer">
                지표면 출처·이용조건
              </a>
            </>
          )}
        </details>
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
