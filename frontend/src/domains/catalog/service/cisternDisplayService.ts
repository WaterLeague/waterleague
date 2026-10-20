import type { MapPoint } from '../entity/facilityFootprint';
import { CatalogError } from '../exception/CatalogError';

// 건물 외측의 표시 위치다. 부지 소유·배관·시공 가능성을 판정하지 않는다.
export function cisternDisplay(
  cell: { polygons?: MapPoint[][][]; coordinates?: MapPoint[] },
  areaM2: number
) {
  const points = (cell.polygons ?? [[cell.coordinates ?? []]]).flatMap((p) => p[0]);
  if (!points.length || !Number.isFinite(areaM2) || areaM2 <= 0)
    throw new CatalogError('INVALID_DATA');
  const east = points.reduce((a, b) => (b[0] > a[0] ? b : a));
  const widthM = Math.sqrt(areaM2 * 0.01);
  const center: MapPoint = [east[0] + widthM / 2 + 0.8, east[1]];
  return { center, roof: east, widthM, heightM: 1, capacityM3: areaM2 * 0.01 };
}
