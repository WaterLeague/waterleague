import type { City } from '../entity/city';
import { inBuildingRing } from './buildingSelectionService';
export function viewingDistrict(districts: City['districts'], point: [number, number]) {
  return districts.find((d) =>
    d.polygons.some(
      (polygon) =>
        inBuildingRing(point, polygon[0]) &&
        !polygon.slice(1).some((hole) => inBuildingRing(point, hole))
    )
  );
}
