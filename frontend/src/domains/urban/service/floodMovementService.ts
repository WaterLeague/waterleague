import { stronger } from './floodFieldService';
import type { FloodContact, FloodRoute } from './floodFieldService';
export type FloodAction =
  'moving' | 'braking' | 'stopped' | 'avoiding' | 'evacuating' | 'stranded' | 'exposed';
export type FloodMotion = {
  arc: number;
  direction: number;
  action: FloodAction;
  contact: FloodContact | null;
  moving: boolean;
};
const wrap = (v: number, length: number) => ((v % length) + length) % length;
export function floodMotion(
  route: FloodRoute,
  home: number,
  travel: number,
  direction: number,
  walking: boolean,
  speed: number,
  queue: number,
  brakingSpeed = speed
): FloodMotion {
  const { length, bands } = route,
    margin = walking ? 1 : 4;
  const result = (
    arc: number,
    heading: number,
    action: FloodAction,
    contact: FloodContact | null,
    moving: boolean
  ): FloodMotion => ({ arc, direction: heading, action, contact, moving });
  if (!bands.length)
    return result(wrap(home + direction * travel, length), direction, 'moving', null, speed > 0);
  const wet = bands.find((b) => home >= b.from && home <= b.to);
  if (wet) {
    const contact = route.samples
      .filter((b) => home >= b.from && home <= b.to)
      .map((b) => b.contact)
      .reduce(
        stronger,
        wet.contact.kind === 'record'
          ? wet.contact
          : { kind: 'record', depth: null, speed: null, hazard: null }
      );
    if (!walking) return result(home, direction, 'exposed', contact, false);
    if ((contact.hazard ?? 0) >= 4) return result(home, direction, 'stranded', contact, false);
    const options = [wet.from - margin, wet.to + margin].filter(
      (p) =>
        p >= margin &&
        p <= length - margin &&
        !bands.some((b) => p >= b.from - margin / 2 && p <= b.to + margin / 2)
    );
    const reachable = options.filter(
      (p) =>
        !route.samples.some(
          (b) =>
            (b.contact.hazard ?? 0) >= 4 && b.from < Math.max(home, p) && b.to > Math.min(home, p)
        )
    );
    reachable.sort((a, b) => Math.abs(a - home) - Math.abs(b - home));
    if (!reachable.length) return result(home, direction, 'stranded', contact, false);
    const target = reachable[0],
      heading = target >= home ? 1 : -1,
      distance = Math.abs(target - home);
    return result(
      home + heading * Math.min(travel, distance),
      heading,
      travel < distance ? 'evacuating' : 'avoiding',
      contact,
      travel < distance
    );
  }
  const ahead = bands
    .map((b) => ({
      band: b,
      distance: direction > 0 ? wrap(b.from - home, length) : wrap(home - b.to, length),
    }))
    .sort((a, b) => a.distance - b.distance)[0];
  if (!walking) {
    // 교통 관측 속력이 바뀌어도 누적 이동량의 감속 곡선은 바꾸지 않는다.
    const limit = Math.max(0, ahead.distance - margin - queue),
      slow = Math.min(limit, brakingSpeed * 3);
    let moved = travel;
    if (slow > 0 && travel > limit - slow)
      moved = limit - slow * Math.exp(-(travel - (limit - slow)) / slow);
    moved = Math.min(limit, moved);
    if (limit - moved < 0.15) moved = limit;
    const stopping = limit - moved <= 0.15;
    return result(
      wrap(home + direction * moved, length),
      direction,
      stopping ? 'stopped' : travel > limit - slow ? 'braking' : 'moving',
      ahead.band.contact,
      !stopping && speed > 0
    );
  }
  const left = bands.filter((b) => b.to < home).at(-1),
    right = bands.find((b) => b.from > home);
  const lo = Math.min(home, left ? left.to + margin : 0),
    hi = Math.max(home, right ? right.from - margin : length),
    span = hi - lo;
  if (span < 1e-6) return result(home, direction, 'stranded', (left ?? right)!.contact, false);
  const phase = wrap(home - lo + direction * travel, span * 2),
    forward = phase < span;
  const arc = lo + (forward ? phase : span * 2 - phase),
    heading = (forward ? 1 : -1) * direction;
  const interacting = travel >= Math.max(0, ahead.distance - margin - speed * 3);
  return result(
    arc,
    heading,
    interacting ? 'avoiding' : 'moving',
    interacting ? ahead.band.contact : null,
    speed > 0
  );
}
export type FloodStats = { stopped: number; exposed: number; avoiding: number; stranded: number };
export const emptyFloodStats: FloodStats = { stopped: 0, exposed: 0, avoiding: 0, stranded: 0 };
