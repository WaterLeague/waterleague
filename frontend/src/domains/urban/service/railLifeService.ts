import type { StreetPath } from './streetLifeService';
import { distanceToStreet, pathPosition, stableSeed } from './streetLifeService';
export const TRAIN_CAR_LENGTH_M = 18;
function pairedRailTracks(paths: StreetPath[]) {
  const used = new Set<number>();
  const result: { index: number; direction: number }[][] = [];
  const centers = paths.map((p) => pathPosition(p, p.length / 2, 0, 1));
  const pairs: { a: number; b: number; distance: number }[] = [];
  for (let a = 0; a < paths.length; a++)
    for (let b = a + 1; b < paths.length; b++) {
      if (paths[a].road.nativeRailKind !== paths[b].road.nativeRailKind) continue;
      const p = centers[a],
        q = centers[b];
      if (Math.abs(Math.cos(p.angle - q.angle)) < 0.95) continue;
      const d = Math.max(
        distanceToStreet(paths[a], q.x, q.y),
        distanceToStreet(paths[b], p.x, p.y)
      );
      if (d >= 2.8 && d <= 12) pairs.push({ a, b, distance: d });
    }
  for (const { a, b } of pairs.sort((x, y) => x.distance - y.distance || x.a - y.a || x.b - y.b)) {
    if (used.has(a) || used.has(b)) continue;
    const p = centers[a],
      q = centers[b];
    const dx = Math.sin(p.angle),
      dy = -Math.cos(p.angle);
    const side = dx * (q.y - p.y) - dy * (q.x - p.x);
    const forward = side > 0 ? 1 : -1;
    const alignment = Math.cos(p.angle - q.angle) >= 0 ? 1 : -1;
    // 원 좌표 저장 순서와 무관하게 서로 다른 평행 선로에 반대 진행 방향을 배정한다.
    used.add(a);
    used.add(b);
    result.push([
      { index: a, direction: forward },
      { index: b, direction: -forward * alignment },
    ]);
  }
  return result;
}
export function pairedRailDirections(paths: StreetPath[]) {
  return new Map(
    pairedRailTracks(paths).flatMap((pair) =>
      pair.map((p) => [paths[p.index].road.id, p.direction] as const)
    )
  );
}
export function railLineKey(path: StreetPath) {
  const name = path.road.nativeRailName?.replace(/\s+/g, '') ?? '';
  const metro = name.match(/(?:서울)?(?:도시철도|지하철|메트로)?(\d+)호선/);
  if (metro) return 'metro:' + metro[1];
  return name.replaceAll(',', '') || 'unnamed:' + path.road.nativeRailKind;
}
type RailRun = { tracks: { path: StreetPath; direction?: number }[]; start: number; end: number };
export type RailService = { id: string; runs: RailRun[]; duration: number };
export function railServices(paths: StreetPath[]): RailService[] {
  const lines = new Map<string, StreetPath[]>();
  for (const path of paths) {
    const key = railLineKey(path);
    if (!lines.has(key)) lines.set(key, []);
    if (path.length >= 45) lines.get(key)!.push(path);
  }
  return [...lines]
    .map(([id, source]) => {
      const paths = [...new Map(source.map((p) => [p.road.id, p])).values()].sort((a, b) =>
        a.road.id.localeCompare(b.road.id)
      );
      const pairs = pairedRailTracks(paths);
      const paired = new Set(pairs.flat().map((p) => p.index));
      const tracks = [
        ...pairs.map((pair) =>
          pair.map((p) => ({ path: paths[p.index], direction: p.direction as number | undefined }))
        ),
        ...paths.flatMap((path, i) =>
          paired.has(i) ? [] : [[{ path, direction: undefined as number | undefined }]]
        ),
      ].sort((a, b) => a[0].path.road.id.localeCompare(b[0].path.road.id));
      let duration = 0;
      const runs = tracks.map((tracks) => {
        const start = duration;
        duration +=
          Math.max(
            ...tracks.map(
              ({ path }) =>
                (path.length + Math.min(4, Math.max(1, Math.floor(path.length / 50))) * 20) /
                (path.road.nativeRailKind === 'subway' ? 10 : 12)
            )
          ) + 2;
        return { tracks, start, end: duration };
      });
      return { id, runs, duration };
    })
    .filter((s) => s.duration > 0);
}
export function activeRailTrains(services: RailService[], seconds: number) {
  return services.flatMap((service) => {
    const time = seconds + stableSeed(service.id) * service.duration;
    const phase = ((time % service.duration) + service.duration) % service.duration;
    const run = service.runs.find((run) => phase >= run.start && phase < run.end)!;
    // 원 선분별 생성 대신 노선별 한 운행 구간만 점유해 방향별 한 편성을 보장한다.
    return run.tracks.map(({ path, direction }) => ({
      path,
      serviceId: service.id,
      cars: trainCarriages(
        path,
        phase - run.start,
        direction ?? (Math.floor(time / service.duration) % 2 === 0 ? 1 : -1),
        true
      ),
    }));
  });
}
export function trainCarriages(
  path: StreetPath,
  seconds: number,
  assignedDirection?: number,
  startAtEntry = false
) {
  const count = Math.min(4, Math.max(1, Math.floor(path.length / 50)));
  const seed = stableSeed(path.road.id);
  const cycle = path.length + count * 20;
  const speed = path.road.nativeRailKind === 'subway' ? 10 : 12;
  const progress = seconds * speed + (startAtEntry ? 0 : seed * cycle);
  // 단선은 편성 전체가 나간 뒤 반대 방향으로 진입해 정면 중첩을 피한다.
  const direction = assignedDirection ?? (Math.floor(progress / cycle) % 2 === 0 ? 1 : -1);
  const head = startAtEntry ? progress : ((progress % cycle) + cycle) % cycle;
  const result = [];
  for (let car = 0; car < count; car++) {
    const along = head - car * 20;
    if (along < 9 || along > path.length - 9) continue;
    const distance = direction > 0 ? along : path.length - along;
    const center = pathPosition(path, distance, 0, direction);
    const front = pathPosition(path, distance + 8 * direction, 0, direction);
    const back = pathPosition(path, distance - 8 * direction, 0, direction);
    result.push({ center, front, back, car, direction, distance });
  }
  return result;
}
