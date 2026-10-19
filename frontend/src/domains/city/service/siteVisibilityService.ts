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

export const availableSiteColor = '#84c9ac';
export const selectedSiteColor = '#ffd56d';
export function siteAppearance({
  eligible,
  matches,
  selected,
  installed,
  otherDistrict,
}: {
  eligible: boolean;
  matches: boolean;
  selected: boolean;
  installed: boolean;
  otherDistrict: boolean;
}) {
  return {
    color: selected
      ? selectedSiteColor
      : installed
        ? '#367c51'
        : eligible && matches
          ? availableSiteColor
          : '#9caaa1',
    opacity: selected ? 1 : buildingOpacity(eligible && matches, otherDistrict),
    fillOpacity: selected ? 0.24 : 0.42,
    outlineOpacity: selected ? 1 : 0.8,
  };
}
