import { insideRainArea } from '../../rainfall/service/rainEffectService';
import type { UrbanArea, LivePlace } from '../entity/liveUrban';
export function visibleLiveAreas(areas: UrbanArea[], center: [number, number], distance: number) {
  if (distance >= 8500) return [];
  const radius = Math.max(750, Math.min(2800, distance));
  const separation = (area: UrbanArea) =>
    Math.hypot(
      Math.max(area.bounds[0] - center[0], 0, center[0] - area.bounds[2]),
      Math.max(area.bounds[1] - center[1], 0, center[1] - area.bounds[3])
    );
  return areas
    .filter((a) => separation(a) <= radius)
    .sort(
      (a, b) => separation(a) - separation(b) || a.areaKm2 - b.areaKm2 || a.id.localeCompare(b.id)
    )
    .slice(0, 6);
}
export function livePlaceAt(places: LivePlace[], x: number, y: number) {
  let selected: LivePlace | undefined;
  for (const place of places) {
    const b = place.bounds;
    if (
      x < b[0] ||
      y < b[1] ||
      x > b[2] ||
      y > b[3] ||
      (selected && selected.areaKm2 <= place.areaKm2)
    )
      continue;
    if (insideRainArea([x, y], place.polygons)) selected = place;
  }
  return selected;
}
export function freshReading<T extends { retrievedAt: string; validUntil: string }>(
  reading: T | null | undefined,
  now: number
): T | null {
  return reading &&
    Date.parse(reading.retrievedAt) <= now + 120000 &&
    now < Date.parse(reading.validUntil)
    ? reading
    : null;
}
