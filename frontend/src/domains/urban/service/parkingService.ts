import type { ParkingData, ParkingLot } from '../entity/parking';
import { streetPath, type StreetPath } from './streetLifeService';
import { inBuildingRing } from '../../city/service/buildingSelectionService';
import { triangleIntersection } from './floodFieldService';
import type { InstallationLayout, SharedSite } from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import { placementFootprint } from '../../catalog/service/facilityGeometryService';
import type { Street } from '../entity/urban';

export function parkingDisplayRoads(roads: Street[], parking: ParkingData) {
  const widths = new Map(parking.displayRoadWidths.map((road) => [road.id, road.widthM]));
  return roads.map((road) => {
    const widthM = widths.get(road.id);
    return road.layer === undefined &&
      road.bridge &&
      road.widthSource === 'DISPLAY_ASSUMPTION' &&
      widthM != null
      ? { ...road, widthM }
      : road;
  });
}

export type ParkingObstacleSite = Pick<
  SharedSite,
  'districtId' | 'cellId' | 'kind' | 'polygons' | 'areaM2'
> & {
  physicalInputs?: Pick<NonNullable<SharedSite['physicalInputs']>, 'swaleDesign' | 'trenchDesign'>;
};
export function parkingOutsideFacilities(
  lots: ParkingLot[],
  sites: ParkingObstacleSite[],
  installed: ReadonlyMap<string, InstallationLayout>
) {
  const obstacles = sites.flatMap((site) => {
    const placement = installed.get(siteKey(site));
    return site.kind === 'GROUND' && placement && placement.facilityType !== 'PERMEABLE_PAVEMENT'
      ? placementFootprint(site, placement).polygons
      : [];
  });
  if (!obstacles.length) return lots;
  return lots.map((lot) => ({
    ...lot,
    slots: lot.slots.filter(
      (slot) =>
        !obstacles.some((polygon) => {
          if (polygon.some((p) => inBuildingRing(p, slot.corners))) return true;
          for (let i = 1; i + 1 < polygon.length; i++)
            for (let j = 1; j < slot.corners.length; j++)
              if (
                triangleIntersection(slot.corners[j - 1], slot.corners[j], [
                  polygon[0],
                  polygon[i],
                  polygon[i + 1],
                ])
              )
                return true;
          return false;
        })
    ),
  }));
}

export function parkingTrafficPaths(
  path: StreetPath,
  routes: ReadonlyMap<string, ParkingData['routes'][number]>
) {
  const rule = routes.get(path.road.id);
  if (!rule || path.road.bridge) return [path];
  return rule.parts.map((coordinates, index) =>
    streetPath({
      ...path.road,
      id: `${path.road.id}:outside-parking:${index}`,
      coordinates,
    })
  );
}
export function visibleParkingLots(lots: ParkingLot[], center: [number, number], distance: number) {
  if (distance > 4500) return [];
  const radius = Math.max(200, Math.min(1800, distance));
  return lots
    .map((lot) => ({
      lot,
      distance: Math.hypot(
        Math.max(lot.bounds[0] - center[0], 0, center[0] - lot.bounds[2]),
        Math.max(lot.bounds[1] - center[1], 0, center[1] - lot.bounds[3])
      ),
    }))
    .filter((value) => value.distance < radius)
    .sort((a, b) => a.distance - b.distance || a.lot.id.localeCompare(b.lot.id))
    .slice(0, 80)
    .map((value) => value.lot);
}
