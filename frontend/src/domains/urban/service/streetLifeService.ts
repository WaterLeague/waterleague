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
export function streetLane(road: Street, walking: boolean, direction: number, seed = 0) {
  if (!walking) {
    const count = road.lanes ?? Math.max(1, Math.round(road.widthM / 3.25));
    const width = Math.max(0, road.widthM - (road.nativeSourceRole ? 1 : 0));
    const laneWidth = width / count;
    if (road.oneway) return (Math.floor(seed * count) + 0.5) * laneWidth - width / 2;
    if (count < 2) return 0;
    const lane = Math.min(Math.floor(count / 2) - 1, Math.floor(seed * Math.floor(count / 2)));
    return (lane + (count % 2 ? 1 : 0.5)) * laneWidth;
  }
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
  const length = path.cumulative[low] - path.cumulative[low - 1];
  const t = length > 0 ? (d - path.cumulative[low - 1]) / length : 0;
  const offsetAt = (index: number) => {
    const points = path.road.coordinates,
      p = points[index];
    const normal = (a: number, b: number) => {
      const dx = points[b][0] - points[a][0],
        dy = points[b][1] - points[a][1],
        length = Math.hypot(dx, dy) || 1;
      return [dy / length, -dx / length];
    };
    const n = normal(Math.max(0, index - 1), index === 0 ? 1 : index),
      m = normal(
        index === points.length - 1 ? index - 1 : index,
        Math.min(points.length - 1, index + 1)
      );
    const length = Math.hypot(n[0] + m[0], n[1] + m[1]) || 1,
      nx = (n[0] + m[0]) / length,
      ny = (n[1] + m[1]) / length;
    const scale =
      Math.min(Math.abs(lane) * 2.5, Math.abs(lane) / Math.max(0.2, nx * m[0] + ny * m[1])) *
      Math.sign(lane) *
      direction;
    return [p[0] + nx * scale, p[1] + ny * scale];
  };
  const left = offsetAt(low - 1),
    right = offsetAt(low);
  // 도색과 이동체가 같은 코너 이음 좌표를 사용해 선분 경계에서 옆 차로로 뛰지 않는다.
  return {
    segment: low - 1,
    x: left[0] + (right[0] - left[0]) * t,
    y: left[1] + (right[1] - left[1]) * t,
    angle: Math.atan2((right[0] - left[0]) * direction, -(right[1] - left[1]) * direction),
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
  const lane = streetLane(path.road, walking, direction, seed);
  return pathPosition(path, direction < 0 ? path.length - distance : distance, lane, direction);
}
