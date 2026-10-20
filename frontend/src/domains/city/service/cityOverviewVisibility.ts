import type { CityOverview, OverviewBuilding } from '../repository/cityOverviewRepository';
export function overviewBuildings(
  coarse: CityOverview | null,
  fine: CityOverview | null,
  center: [number, number],
  radius: number,
  details: ReadonlySet<string>,
  limit = 80000
): OverviewBuilding[] {
  const tileIds = fine?.tileIds ?? coarse?.tileIds ?? [];
  const near =
    fine?.buildings
      .filter(
        (b) =>
          !details.has(tileIds[b[6]]) &&
          Math.abs(b[0] - center[0]) <= radius &&
          Math.abs(b[1] - center[1]) <= radius
      )
      .sort(
        (a, b) =>
          Math.hypot(a[0] - center[0], a[1] - center[1]) -
          Math.hypot(b[0] - center[0], b[1] - center[1])
      )
      .slice(0, limit) ?? [];
  const cells = new Set(near.map((b) => `${Math.floor(b[0] / 100)}:${Math.floor(b[1] / 100)}`));
  // 확대 범위 밖도 축소 건물로 채우고 상세 타일이 도착한 부분만 교체한다.
  return [
    ...near,
    ...(coarse?.buildings.filter(
      (b) =>
        !details.has(coarse.tileIds[b[6]]) &&
        !cells.has(`${Math.floor(b[0] / 100)}:${Math.floor(b[1] / 100)}`)
    ) ?? []),
  ];
}
