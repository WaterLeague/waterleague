import { useMemo } from 'react';
import type { ParkingData } from '../entity/parking';
import type { InstallationLayout, SharedSite } from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import {
  visibleParkingLots,
  parkingOutsideFacilities,
  type ParkingObstacleSite,
} from '../service/parkingService';

export function useParkingLots(
  parking: ParkingData | null | undefined,
  center: [number, number],
  distance: number,
  sites: SharedSite[],
  installed: ReadonlyMap<string, InstallationLayout>
) {
  const key = JSON.stringify(
    visibleParkingLots(parking?.lots ?? [], center, distance)
      .map((lot) => lot.id)
      .sort()
  );
  const visible = useMemo(() => {
    const ids = new Set<string>(JSON.parse(key));
    return parking?.lots.filter((lot) => ids.has(lot.id)) ?? [];
  }, [parking, key]);
  // 후보 재조회·거리 순서 변화는 주차장 형상을 바꾸지 않는다.
  const obstacleKey = JSON.stringify(
    sites
      .filter((site) => {
        const placement = installed.get(siteKey(site));
        return (
          site.kind === 'GROUND' && placement && placement.facilityType !== 'PERMEABLE_PAVEMENT'
        );
      })
      .map(({ districtId, cellId, kind, coordinates, areaM2, physicalInputs }) => ({
        districtId,
        cellId,
        kind,
        coordinates,
        areaM2,
        physicalInputs: {
          swaleDesign: physicalInputs?.swaleDesign,
          trenchDesign: physicalInputs?.trenchDesign,
        },
      }))
      .sort((a, b) => siteKey(a).localeCompare(siteKey(b)))
  );
  const obstacles = useMemo(() => JSON.parse(obstacleKey) as ParkingObstacleSite[], [obstacleKey]);
  return useMemo(
    () => parkingOutsideFacilities(visible, obstacles, installed),
    [visible, obstacles, installed]
  );
}
