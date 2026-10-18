import type { LiveRainfall } from '../entity/liveRainfall';

export type RainStation = LiveRainfall['districts'][number];
export function observationFresh(station: RainStation, now: number) {
  if (!station.rainObservedAt) return false;
  const age = now - Date.parse(station.rainObservedAt);
  return age >= 0 && age <= 300000;
}
export function isRaining(station: RainStation, now: number) {
  return observationFresh(station, now) && station.rainState === 'WET';
}
export function rainCondition(station: RainStation, now: number) {
  if (!observationFresh(station, now)) return '현재 강수 확인 불가';
  if (station.rainState === 'WET') return '최근 관측에서 비 감지';
  if (station.rainState === 'SNOW') return '최근 관측에서 눈 감지';
  if (station.rainState === 'NO_RAIN_DETECTED') return '최근 관측에서 강수 미감지';
  return '현재 강수 확인 불가';
}

export function rainEvidenceLabel(station: RainStation) {
  if (station.rainEvidence === 'AWS_PRESENT_WEATHER')
    return `현천 관측 · 코드 ${station.presentWeatherCode ?? '미확인'}`;
  if (station.rainEvidence === 'AWS_RAIN_SENSOR') return '강수감지 센서';
  if (station.rainEvidence === 'AWS_MINUTE_INCREMENT') return '연속 1분 누적량 증가';
  return '강수감지·현천 관측 없음 · 0mm만으로 비 없음 판정 불가';
}

type Point = [number, number];
export type RainPolygons = Point[][][];
// 밀도는 시각 표현용이다. 관측량·점수·물리 입력에는 적용하지 않는다.
export function rainVisualDensity(oneMinuteMm: number | null | undefined) {
  if (oneMinuteMm == null || !Number.isFinite(oneMinuteMm) || oneMinuteMm <= 0) return 0.25;
  return Math.min(1.6, 0.25 + Math.sqrt(oneMinuteMm * 60) / 10);
}
// 작은 카메라 이동은 같은 입자 영역을 재사용하고 실제 관측 구 경계는 유지한다.
export function rainSamplingWindow(center: Point, distance: number) {
  const scale = 2 ** Math.ceil(Math.log2(Math.max(256, distance)));
  return {
    x: Math.round(center[0] / scale) * scale,
    y: Math.round(center[1] / scale) * scale,
    radius: scale * 1.5,
    scale,
  };
}
function inRing([x, y]: Point, ring: Point[]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [a, b] = ring[i],
      [c, d] = ring[j];
    if (b > y !== d > y && x < ((c - a) * (y - b)) / (d - b) + a) inside = !inside;
  }
  return inside;
}
export function insideRainArea(point: Point, polygons: RainPolygons) {
  return polygons.some(
    (p) => inRing(point, p[0]) && !p.slice(1).some((hole) => inRing(point, hole))
  );
}

// 입자는 표현용이며 관측량이나 물리 계산에 사용하지 않는다.
export function rainParticleSeeds(
  polygons: RainPolygons,
  center: Point,
  radius: number,
  count: number
) {
  let west = Infinity,
    east = -Infinity,
    south = Infinity,
    north = -Infinity;
  for (const polygon of polygons)
    for (const [x, y] of polygon[0]) {
      west = Math.min(west, x);
      east = Math.max(east, x);
      south = Math.min(south, y);
      north = Math.max(north, y);
    }
  west = Math.max(west, center[0] - radius);
  east = Math.min(east, center[0] + radius);
  south = Math.max(south, center[1] - radius);
  north = Math.min(north, center[1] + radius);
  const result: { point: Point; phase: number }[] = [];
  if (west >= east || south >= north) return result;
  let seed = 173;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let i = 0; i < count * 12 && result.length < count; i++) {
    const point: Point = [west + (east - west) * random(), south + (north - south) * random()];
    const phase = random();
    if (insideRainArea(point, polygons)) result.push({ point, phase });
  }
  return result;
}
