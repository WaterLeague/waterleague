export const otherDistrictOpacity = 0.16;
export const unavailableBuildingOpacity = 0.2;
export function buildingOpacity(eligible: boolean, otherDistrict: boolean) {
  return otherDistrict
    ? eligible
      ? otherDistrictOpacity
      : 0.07
    : eligible
      ? 1
      : unavailableBuildingOpacity;
}
export function occupiedRoofSource(
  districtId: string,
  cellId: string,
  legacy: Record<string, string[]>
) {
  if (/^RW\d+$/.test(cellId)) return ['way/' + cellId.slice(2)];
  if (/^RR\d+$/.test(cellId)) return ['relation/' + cellId.slice(2)];
  return legacy[districtId + ':' + cellId] ?? [];
}
