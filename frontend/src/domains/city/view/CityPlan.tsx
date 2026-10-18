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
import { infrastructureColor } from '../../infrastructure/service/infrastructureService';
import { InfrastructureFootprintsPlan } from '../../infrastructure/view/InfrastructureFootprints';
import type { TraceTile } from '../../floodtrace/entity/floodTrace';
import { FloodTracePlan } from '../../floodtrace/view/FloodTraceLayer';
import { SurfacePlan } from '../../surface/view/SurfaceLayer';
import type { SurfaceFrame, SurfaceMetric } from '../../surface/entity/surface';
import { CisternLayoutPlan } from '../../installation/view/CisternLayoutPlan';
import type { CisternGeometryPreview } from '../../installation/dto/cisternLayoutDto';

type Props = {
  cisternGeometry?: CisternGeometryPreview | null;
  planningRoles?: ReadonlyMap<string, CisternSiteRole>;
  preview?: { site: SharedSite; placement: Placement } | null;
  surfaceFrame?: SurfaceFrame | null;
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
  onCamera: (view: PlanView) => void;
  onNavigate: (view: PlanView) => void;
  camera: PlanView;
  rainAmounts: ReadonlyMap<string, number | null>;
};
export const CityPlan = memo(function CityPlan({
  preview = null,
  surfaceFrame = null,
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
  const paths = useMemo(
    () => ({
      boundary: polygonPath(city.boundary),
      districts: new Map(city.districts.map((d) => [d.id, polygonPath(d.polygons)])),
      roads: city.roads
        .map((r) => r.coordinates.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' '))
        .join(' '),
      surfaces: city.surfaces.map((s) => ({ kind: s.kind, path: polygonPath(s.polygons) })),
    }),
    [city]
  );
  const buildings = useMemo(
    () =>
      [
        ...new Map(
          [...city.overviewBuildings, ...tiles.flatMap((t) => t.buildings)].map((b) => [b.id, b])
        ).values(),
      ].map((b) => ({ building: b, path: polygonPath(b.polygons) })),
    [city, tiles]
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
      buildings.map(({ building: b, path }) => (
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
            opacity={buildingOpacity(
              !site.existingInfrastructure &&
                (planningRoles?.has(siteKey(site)) ||
                  !facilityType ||
                  site.allowedTypes.includes(facilityType)) &&
                (!installed || installed.ownerId === viewerId),
              !!ownDistrictId && ownDistrictId !== site.districtId
            )}
            onClick={() => onSite(siteKey(site))}
          >
            <title>
              {site.name} ·{' '}
              {installed
                ? '설치됨'
                : site.existingInfrastructure
                  ? '공개 저류 영역 · 신규 설치 제외'
                  : '빈 위치'}
            </title>
          </path>
        );
      }),
    [
      sites,
      installationBySite,
      sitePaths,
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
      <path
        d={paths.roads}
        fill="none"
        stroke="#bfc3b4"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
        pointerEvents="none"
      />
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
                {districtScores.get(d.id) ?? '평가 대기'}
              </tspan>
            )}
          </text>
        ))}
      {buildingLayer}
      <InfrastructureFootprintsPlan assets={publicAssets} selectedId={selectedAssetId} />
      {siteLayer}
      {facilityLayer}
      {cisternGeometry && <CisternLayoutPlan geometry={cisternGeometry} />}
      <FloodTracePlan tiles={traceTiles} />
      <SurfacePlan frame={surfaceFrame} metric={surfaceMetric} />
      {installations.map((i) => (
        <circle
          key={i.id}
          cx={i.center[0]}
          cy={-i.center[1]}
          r={overview ? 95 : Math.max(2, focus.distance * 0.008)}
          fill="#327b4f"
          opacity={buildingOpacity(
            (!facilityType || i.facilityType === facilityType) && i.ownerId === viewerId,
            !!ownDistrictId && i.districtId !== ownDistrictId
          )}
          onClick={() => void onSite(siteKey(i))}
        >
          <title>
            {i.ownerName} · {facilities[i.facilityType].name}
          </title>
        </circle>
      ))}
      {publicAssets.map((asset) => (
        <circle
          key={asset.id}
          cx={asset.center[0]}
          cy={-asset.center[1]}
          r={1}
          fill={infrastructureColor(asset)}
          stroke={asset.id === selectedAssetId ? '#dda62e' : infrastructureColor(asset)}
          strokeWidth={asset.id === selectedAssetId ? 15 : 10}
          vectorEffect="non-scaling-stroke"
          onClick={(event) => {
            event.stopPropagation();
            onAsset(asset);
          }}
        >
          <title>{asset.name} · 공개 참고 위치</title>
        </circle>
      ))}
      <LiveRainPlan
        districts={wetDistricts}
        amounts={rainAmounts}
        scale={box.height}
        animate={animateRain}
      />
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
