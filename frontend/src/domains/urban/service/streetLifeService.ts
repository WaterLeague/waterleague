import type { Street } from '../entity/urban';
export function sidewalkSides(road: Street) {
  const present = (value: string | undefined, side: string) => {
    if (value !== undefined) return value === 'yes' || value === 'both' || value === side;
    return road.sidewalk === 'yes' || road.sidewalk === 'both' || road.sidewalk === side;
  };
  return [present(road.sidewalkLeft, 'left'), present(road.sidewalkRight, 'right')];
}
export function hasInlineSidewalk(road: Street) {
  return sidewalkSides(road).some(Boolean);
}
export function streetLane(road: Street, walking: boolean, direction: number) {
  if (!walking) return Math.min(2.5, road.widthM * 0.23);
  if (!road.motor) return 0;
  const [left, right] = sidewalkSides(road),
    offset = road.widthM / 2 + 0.7;
  return left && !right ? -offset * direction : right && !left ? offset * direction : offset;
}
export function stableSeed(id: string) {
  let value = 2166136261;
  for (let i = 0; i < id.length; i++) value = Math.imul(value ^ id.charCodeAt(i), 16777619);
  return (value >>> 0) / 4294967296;
}
export function streetPath(road: Street) {
  const cumulative = [0];
  for (let i = 1; i < road.coordinates.length; i++)
    cumulative.push(
      cumulative[i - 1] +
        Math.hypot(
          road.coordinates[i][0] - road.coordinates[i - 1][0],
          road.coordinates[i][1] - road.coordinates[i - 1][1]
        )
    );
  return { road, cumulative, length: cumulative.at(-1)! };
}
export type StreetPath = ReturnType<typeof streetPath>;
export function streetActorRoutes(path: StreetPath) {
  const walking =
    (path.road.walk && path.road.class !== 'cycleway') ||
    (path.road.motor && hasInlineSidewalk(path.road) && !/motorway|trunk/.test(path.road.class));
  return [
    ...(walking ? [{ path, walking: true }] : []),
    ...(path.road.motor ? [{ path, walking: false }] : []),
  ];
}
export function distanceToStreet(path: StreetPath, x: number, y: number) {
  let nearest = Infinity;
  for (let i = 1; i < path.road.coordinates.length; i++) {
    const a = path.road.coordinates[i - 1],
      b = path.road.coordinates[i];
    const dx = b[0] - a[0],
      dy = b[1] - a[1],
      length2 = dx * dx + dy * dy;
    const t =
      length2 > 0 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / length2)) : 0;
    nearest = Math.min(nearest, Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy));
  }
  return nearest;
}
export function pathPosition(path: StreetPath, distance: number, lane: number, direction: number) {
  const d = Math.max(0, Math.min(path.length, distance));
  let low = 1,
    high = path.cumulative.length - 1;
  while (low < high) {
    const m = (low + high) >> 1;
    if (path.cumulative[m] < d) low = m + 1;
    else high = m;
  }
  const a = path.road.coordinates[low - 1],
    b = path.road.coordinates[low];
  const length = path.cumulative[low] - path.cumulative[low - 1];
  const t = length > 0 ? (d - path.cumulative[low - 1]) / length : 0;
  const dx = length > 0 ? (b[0] - a[0]) / length : 1,
    dy = length > 0 ? (b[1] - a[1]) / length : 0;
  // 한국의 우측 통행은 진행 방향의 오른쪽으로 이동시킨다.
  return {
    segment: low - 1,
    x: a[0] + (b[0] - a[0]) * t + dy * lane * direction,
    y: a[1] + (b[1] - a[1]) * t - dx * lane * direction,
    angle: Math.atan2(dx * direction, -dy * direction),
  };
}
export function streetSpeed(path: StreetPath, seed: number, walking: boolean) {
  return walking ? 1.15 + seed * 0.35 : /motorway|trunk/.test(path.road.class) ? 15 : 6 + seed * 3;
}
export function advanceTravel(
  previous: { time: number; distance: number },
  time: number,
  speed: number
) {
  const elapsed = Math.max(0, Math.min(2, time - previous.time));
  return { time, distance: previous.distance + elapsed * speed };
}
export function movingPosition(path: StreetPath, time: number, seed: number, walking: boolean) {
  return travellingPosition(path, time * streetSpeed(path, seed, walking), seed, walking);
}
export function travellingPosition(
  path: StreetPath,
  travel: number,
  seed: number,
  walking: boolean
) {
  const direction = (!walking && path.road.oneway) || (seed > 0.5 ? 1 : -1);
  const distance = (((travel + seed * path.length) % path.length) + path.length) % path.length;
  const lane = streetLane(path.road, walking, direction);
  return pathPosition(path, direction < 0 ? path.length - distance : distance, lane, direction);
}
