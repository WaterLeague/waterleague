import { InstallationSymbolsPlan } from '../../installation/view/InstallationSymbolsPlan';
import { InstallationNameplatesPlan } from '../../installation/view/InstallationNameplatesPlan';
import { installationSymbols } from '../../installation/service/installationSymbolsService';
import type { PublicFrame } from '../../surface/service/publicSurfaceService';
import { publicInfrastructureBuildingIds } from '../../infrastructure/service/infrastructureService';
import { memo, useMemo } from 'react';
import type { City, CityBuilding, CityFocus, CityTile } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import type { SharedSite, SharedInstallation } from '../../installation/entity/installation';
import type { FacilityType, Placement } from '../../game/entity/game';
import { placementFootprint } from '../../catalog/service/facilityGeometryService';
import { siteKey } from '../../installation/entity/installation';
import { facilities } from '../../game/service/gameService';
import { polygonPath } from '../../catalog/service/mapGeometryService';
import { buildingOpacity, otherDistrictOpacity } from '../service/siteVisibilityService';
import {
  cisternSiteColors,
  type CisternSiteRole,
} from '../../installation/service/cisternPlanService';
import { inBuildingRing } from '../service/buildingSelectionService';
import { LiveRainPlan } from '../../rainfall/view/LiveRainPlan';
import { detailLabelDistance } from '../service/cityService';
import { usePlanNavigation } from '../controller/usePlanNavigation';
import type { PlanView } from '../service/planNavigationService';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { InfrastructureSymbolsPlan } from '../../infrastructure/view/InfrastructureSymbolsPlan';
import { InfrastructureFootprintsPlan } from '../../infrastructure/view/InfrastructureFootprints';
import type { TraceTile } from '../../floodtrace/entity/floodTrace';
import { FloodTracePlan } from '../../floodtrace/view/FloodTraceLayer';
import { SurfacePlan } from '../../surface/view/SurfaceLayer';
import type { SurfaceFrame, SurfaceMetric } from '../../surface/entity/surface';
import { CisternLayoutPlan } from '../../installation/view/CisternLayoutPlan';
import type { CisternGeometryPreview } from '../../installation/dto/cisternLayoutDto';
import type { Street } from '../../urban/entity/urban';
import type { ParkingData } from '../../urban/entity/parking';
import { visibleParkingLots, parkingOutsideFacilities } from '../../urban/service/parkingService';

type Props = {
  streets: Street[];
  parking: ParkingData | null;
  cisternGeometry?: CisternGeometryPreview | null;
  planningRoles?: ReadonlyMap<string, CisternSiteRole>;
  preview?: { site: SharedSite; placement: Placement } | null;
  surfaceFrame?: SurfaceFrame | null;
  publicSurfaceFrames?: PublicFrame[];
  surfaceMetric?: SurfaceMetric;
  traceTiles: TraceTile[];
  publicAssets: InfrastructureAsset[];
  selectedAssetId: string;
  onAsset: (asset: InfrastructureAsset) => void;
  city: City;
  focus: CityFocus;
  regions: CityPlayRegion[];
  tiles: CityTile[];
  selected: string;
  ownDistrictId: string | null;
  viewerId: string | null;
  sites: SharedSite[];
  installations: SharedInstallation[];
  installationBySite: ReadonlyMap<string, SharedInstallation>;
  selectedSite: string;
  facilityType: FacilityType | '';
  eligibleRoofs: ReadonlySet<string>;
  occupiedRoofs: ReadonlySet<string>;
  wetDistricts: City['districts'];
  animateRain: boolean;
  districtScores: Map<string, string> | null;
  onDistrict: (id: string) => void;
  onSite: (key: string) => void;
  onBuilding: (districtId: string, building: CityBuilding) => void;
  onStreet?: (sourceId: string, point: [number, number]) => void;
  onParking: (sourceId: string, point: [number, number]) => void;
  onCamera: (view: PlanView) => void;
  onNavigate: (view: PlanView) => void;
  camera: PlanView;
  rainAmounts: ReadonlyMap<string, number | null>;
};
export const CityPlan = memo(function CityPlan({
  streets,
  parking,
  preview = null,
  surfaceFrame = null,
  publicSurfaceFrames = [],
  surfaceMetric = 'depth',
  traceTiles,
  publicAssets,
  selectedAssetId,
  onAsset,
  city,
  focus: requestedFocus,
  regions,
  tiles,
  selected,
  ownDistrictId,
  viewerId,
  sites,
  installations,
  installationBySite,
  selectedSite,
  facilityType,
  eligibleRoofs,
  occupiedRoofs,
  wetDistricts,
  animateRain,
  districtScores,
  onDistrict,
  onSite,
  onBuilding,
  onStreet,
  onParking,
  onCamera,
  onNavigate,
  camera,
  rainAmounts,
  planningRoles,
  cisternGeometry,
}: Props) {
  const {
    svg,
    view: focus,
    box,
    dragging,
    handlers,
  } = usePlanNavigation(requestedFocus, city.bounds, camera, onCamera, onNavigate);
  const overview = focus.distance >= 9000;
  const parkingLots = useMemo(
    () =>
      parkingOutsideFacilities(
        visibleParkingLots(parking?.lots ?? [], focus.center, focus.distance),
        sites,
        installationBySite
      ),
    [parking, focus, sites, installationBySite]
  );
  const parkingSources = useMemo(() => new Set(parkingLots.map((lot) => lot.id)), [parkingLots]);
  const symbols = useMemo(
    () => installationSymbols(installations, sites, viewerId, facilityType, focus.distance),
    [installations, sites, viewerId, facilityType, focus.distance]
  );
  const paths = useMemo(
    () => ({
      boundary: polygonPath(city.boundary),
      districts: new Map(city.districts.map((d) => [d.id, polygonPath(d.polygons)])),
      surfaces: city.surfaces.map((s) => ({ kind: s.kind, path: polygonPath(s.polygons) })),
    }),
    [city]
  );
  const roadPaths = useMemo(
    () =>
      [...streets]
        .sort((a, b) => Number(a.bridge) - Number(b.bridge))
        .map((r) => ({
          id: r.id,
          width: r.widthM,
          walk: r.walk,
          bridge: r.bridge,
          path: r.coordinates.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' '),
        })),
    [streets]
  );
  const publicBuildings = useMemo(
    () => publicInfrastructureBuildingIds(publicAssets),
    [publicAssets]
  );
  const buildings = useMemo(
    () =>
      [
        ...new Map(
          [...city.overviewBuildings, ...tiles.flatMap((t) => t.buildings)].map((b) => [b.id, b])
        ).values(),
      ]
        .filter((b) => !publicBuildings.has(b.id))
        .map((b) => ({ building: b, path: polygonPath(b.polygons) })),
    [city, tiles, publicBuildings]
  );
  const sitePaths = useMemo(
    () => new Map(sites.map((s) => [siteKey(s), polygonPath([[s.coordinates]])])),
    [sites]
  );
  const ownDistrict = city.districts.find((d) => d.id === ownDistrictId);
  const showLabels = focus.distance >= detailLabelDistance;
  function otherBuilding(b: CityBuilding) {
    return (
      !!ownDistrict &&
      !ownDistrict.polygons.some(
        (p) =>
          inBuildingRing(b.center, p[0]) && !p.slice(1).some((h) => inBuildingRing(b.center, h))
      )
    );
  }
  const buildingLayer = useMemo(
    () =>
      buildings
        .filter(
          ({ building: b }) =>
            !facilityType ||
            (facilityType === 'GREEN_ROOF' &&
              eligibleRoofs.has(b.id) &&
              !occupiedRoofs.has(b.id) &&
              !otherBuilding(b))
        )
        .map(({ building: b, path }) => (
          <path
            key={b.id}
            d={path}
            fill="#d9d8cb"
            opacity={buildingOpacity(
              (!facilityType || facilityType === 'GREEN_ROOF') &&
                eligibleRoofs.has(b.id) &&
                !occupiedRoofs.has(b.id),
              otherBuilding(b)
            )}
            stroke="#9eac96"
            strokeWidth={0.5}
            vectorEffect="non-scaling-stroke"
            onClick={() => {
              const d = city.districts.find((d) =>
                d.polygons.some(
                  (p) =>
                    inBuildingRing(b.center, p[0]) &&
                    !p.slice(1).some((h) => inBuildingRing(b.center, h))
                )
              );
              if (d) void onBuilding(d.id, b);
            }}
          >
            <title>{b.id} · 건물 선택</title>
          </path>
        )),
    [buildings, facilityType, eligibleRoofs, occupiedRoofs, ownDistrict, onBuilding, city]
  );
  const facilityLayer = useMemo(() => {
    const values: { site: SharedSite; placement: Placement; preview: boolean }[] = sites.flatMap(
      (site) => {
        const placement = installationBySite.get(siteKey(site));
        return placement ? [{ site, placement, preview: false }] : [];
      }
    );
    if (preview) values.push({ ...preview, preview: true });
    return values.map((value) => {
      const shape = placementFootprint(value.site, value.placement);
      const path = shape.polygons
        .map((p) => p.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' ') + 'Z')
        .join(' ');
      return (
        <path
          key={siteKey(value.site)}
          d={path}
          fill={facilities[value.placement.facilityType].color}
          fillOpacity={value.preview ? 0.55 : 0.9}
          stroke={value.preview ? '#214e67' : '#426a49'}
          strokeWidth={0.25}
          strokeDasharray={value.preview ? '.8 .5' : undefined}
          opacity={buildingOpacity(
            !facilityType || value.placement.facilityType === facilityType,
            !!ownDistrictId && ownDistrictId !== value.site.districtId
          )}
          onClick={() => onSite(siteKey(value.site))}
        />
      );
    });
  }, [sites, installationBySite, preview, facilityType, ownDistrictId, onSite]);
  const siteLayer = useMemo(
    () =>
      sites.map((site) => {
        const installed = installationBySite.get(siteKey(site));
        const parkingSurface =
          site.kind === 'GROUND' && site.sourceIds.some((id) => parkingSources.has(id));
        const highlighted =
          site.cellId === selectedSite ||
          planningRoles?.has(siteKey(site)) ||
          (facilityType && site.allowedTypes.includes(facilityType));
        return (
          <path
            key={siteKey(site)}
            d={sitePaths.get(siteKey(site))}
            fill={
              site.districtId === selected && site.cellId === selectedSite
                ? '#ffd56d'
                : planningRoles?.has(siteKey(site))
                  ? cisternSiteColors[planningRoles.get(siteKey(site))!]
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
            fillOpacity={parkingSurface ? (highlighted ? 0.24 : 0) : 1}
            strokeOpacity={parkingSurface ? (highlighted ? 0.65 : 0) : 1}
            pointerEvents="all"
            opacity={buildingOpacity(
              !site.existingInfrastructure &&
                (planningRoles?.has(siteKey(site)) ||
                  !facilityType ||
                  site.allowedTypes.includes(facilityType)) &&
                (!installed || installed.ownerId !== viewerId),
              !!ownDistrictId && ownDistrictId !== site.districtId
            )}
            onClick={() => onSite(siteKey(site))}
          >
            <title>
              {site.name} ·{' '}
              {installed
                ? '설치됨'
                : site.existingInfrastructure
                  ? '공개 시설 영역 · 신규 설치 제외'
                  : '빈 위치'}
            </title>
          </path>
        );
      }),
    [
      sites,
      installationBySite,
      sitePaths,
      parkingSources,
      selected,
      selectedSite,
      planningRoles,
      facilityType,
      viewerId,
      ownDistrictId,
      onSite,
    ]
  );
  return (
    <svg
      ref={svg}
      {...handlers}
      style={{ touchAction: 'none', userSelect: 'none', cursor: dragging ? 'grabbing' : 'grab' }}
      className="city-plan"
      viewBox={`${box.x} ${box.y} ${box.width} ${box.height}`}
      role="group"
      aria-label="서울 25개 구 플레이 지도"
    >
      <path d={paths.boundary} fill="#dfe3cf" />
      {city.districts.map((d) => (
        <path
          key={d.id}
          d={paths.districts.get(d.id)}
          fill={ownDistrictId === d.id ? '#a3c884' : d.id === selected ? '#c4d6b4' : '#cbd5be'}
          opacity={!ownDistrictId || ownDistrictId === d.id ? 1 : otherDistrictOpacity}
          stroke="#809478"
          strokeWidth={d.id === ownDistrictId ? 75 : 20}
          onClick={() => onDistrict(d.id)}
        >
          <title>{d.name}</title>
        </path>
      ))}
      {paths.surfaces.map((s, i) => (
        <path key={i} d={s.path} fill={s.kind === 'water' ? '#81b1ba' : '#b4c8a3'} />
      ))}
      <g pointerEvents="none">
        {parkingLots.map((lot) => (
          <g key={lot.id}>
            <path d={polygonPath(lot.surfacePolygons)} fill="#858780" fillRule="evenodd" />
            {lot.slots.map((slot, i) => (
              <g key={i}>
                <path
                  d={polygonPath([[slot.corners]])}
                  fill="none"
                  stroke="#e5e0cf"
                  strokeWidth={0.12}
                />
                {slot.seed < 0.65 && (
                  <g
                    transform={`rotate(${(-slot.angle * 180) / Math.PI},${slot.center[0]},${-slot.center[1]})`}
                  >
                    <rect
                      x={slot.center[0] - 0.875}
                      y={-slot.center[1] - 2.05}
                      width={1.75}
                      height={4.1}
                      rx={0.2}
                      fill={slot.seed < 0.3 ? '#dedbd1' : '#345e79'}
                    />
                    <rect
                      x={slot.center[0] - 0.7}
                      y={-slot.center[1] - 1.1}
                      width={1.4}
                      height={2.2}
                      fill="#283b4c"
                    />
                  </g>
                )}
              </g>
            ))}
          </g>
        ))}
      </g>
      <g
        fill="none"
        pointerEvents={facilityType === 'PERMEABLE_PAVEMENT' ? 'stroke' : 'none'}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {roadPaths.map((r) => (
          <g key={r.id}>
            {r.bridge && (
              <path d={r.path} stroke="#c6d0d2" strokeWidth={r.width + 1.1} pointerEvents="none" />
            )}
            <path
              d={r.path}
              stroke={r.bridge ? '#4e606e' : r.walk ? '#b3ae9f' : '#667071'}
              strokeWidth={r.width}
              onClick={(event) => {
                if (dragging || facilityType !== 'PERMEABLE_PAVEMENT' || !onStreet) return;
                const matrix = svg.current?.getScreenCTM();
                if (!matrix) return;
                const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(
                  matrix.inverse()
                );
                event.stopPropagation();
                onStreet(r.id, [point.x, -point.y]);
              }}
            >
              {r.bridge && <title>고가도로 · 지상 주차장과 높이 분리</title>}
            </path>
          </g>
        ))}
      </g>
      {parkingLots.map((lot) => (
        <path
          key={'parking-hit:' + lot.id}
          d={polygonPath(lot.polygons)}
          fill="transparent"
          fillRule="evenodd"
          pointerEvents="all"
          role="button"
          tabIndex={0}
          aria-label="주차장 설치 위치 선택"
          onClick={(event) => {
            if (dragging) return;
            const matrix = svg.current?.getScreenCTM();
            if (!matrix) return;
            const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(
              matrix.inverse()
            );
            event.stopPropagation();
            onParking(lot.id, [point.x, -point.y]);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onParking(lot.id, lot.slots[0]?.center ?? lot.polygons[0][0][0]);
            }
          }}
        />
      ))}
      {showLabels &&
        city.districts.map((d) => (
          <text
            key={d.id}
            x={d.center[0]}
            y={-d.center[1]}
            textAnchor="middle"
            fontSize={overview ? 420 : focus.distance * 0.035}
            fill="#233c35"
          >
            <tspan x={d.center[0]}>{d.name}</tspan>
            {districtScores && (
              <tspan x={d.center[0]} dy="1.3em" fontSize="0.72em">
                {districtScores.get(d.id) ?? ''}
              </tspan>
            )}
          </text>
        ))}
      {buildingLayer}
      <InfrastructureFootprintsPlan
        assets={facilityType ? [] : publicAssets}
        selectedId={selectedAssetId}
        onSelect={onAsset}
      />
      {siteLayer}
      {facilityLayer}
      {cisternGeometry && <CisternLayoutPlan geometry={cisternGeometry} />}
      <FloodTracePlan tiles={traceTiles} />
      <SurfacePlan frame={surfaceFrame} metric={surfaceMetric} />
      {!surfaceFrame &&
        publicSurfaceFrames.map((value) => (
          <SurfacePlan key={value.id} frame={value.frame} metric={surfaceMetric} />
        ))}
      <InstallationSymbolsPlan
        installations={symbols}
        selectedKey={`${selected}:${selectedSite}`}
        ownDistrictId={ownDistrictId}
        scale={box.height * 0.016}
        onSelect={onSite}
      />
      <InfrastructureSymbolsPlan
        distance={focus.distance}
        assets={facilityType ? [] : publicAssets}
        selectedId={selectedAssetId}
        scale={box.height * 0.014}
        onSelect={onAsset}
      />
      <LiveRainPlan
        districts={wetDistricts}
        amounts={rainAmounts}
        scale={box.height}
        animate={animateRain}
      />
      {!facilityType && focus.distance < detailLabelDistance && (
        <InstallationNameplatesPlan
          installations={installations}
          viewerId={viewerId}
          box={box}
          onSelect={onSite}
        />
      )}
      {showLabels &&
        regions.map((r) => (
          <g
            key={r.mapId}
            role="button"
            tabIndex={0}
            aria-label={`${r.districtName} 대표 블록 선택`}
            aria-pressed={r.districtId === selected}
            className="city-plan-pin"
            onClick={() => onDistrict(r.districtId)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onDistrict(r.districtId);
              }
            }}
          >
            <circle
              cx={r.center[0]}
              cy={-r.center[1]}
              r={overview ? 160 : 8}
              fill={r.districtId === selected ? '#173d29' : '#52734b'}
              stroke="#fffdf2"
              strokeWidth={overview ? 60 : 2}
            />
            <title>{r.districtName} · 대표 블록 플레이 가능</title>
          </g>
        ))}
    </svg>
  );
});
