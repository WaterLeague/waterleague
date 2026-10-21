import polygonClipping from 'polygon-clipping';
import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
import { withinBridge } from './nativeBridgeService';
type Point = [number, number];
type Polygons = Point[][][];
type Cut = {
  polygon: Point[][];
  bounds: number[];
  group?: NativeBridgeGroup;
  roles?: string[];
  sourceFids?: number[];
};
const CELL = 500;
// 파생 교차점의 부동소수점 잡음을 0.1mm 표시 격자로 맞춰 겹친 경계의 순환을 막는다.
function snapped(polygons: Polygons): Polygons {
  return polygons.map((p) =>
    p.map((r) => r.map(([x, y]) => [Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000]))
  );
}
function bounds(polygons: Polygons) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const polygon of polygons)
    for (const p of polygon[0]) {
      b[0] = Math.min(b[0], p[0]);
      b[1] = Math.min(b[1], p[1]);
      b[2] = Math.max(b[2], p[0]);
      b[3] = Math.max(b[3], p[1]);
    }
  return b;
}
export class NativeGroundCuts {
  private cells = new Map<string, Cut[]>();
  private sourceWater: boolean;
  constructor(
    groups: NativeBridgeGroup[],
    waterPolygons = groups[0]?.displayWaterPolygons,
    snap = true
  ) {
    this.sourceWater = !!waterPolygons;
    for (const entry of [
      ...groups
        .filter((g) => !g.kinds?.includes('지하차도'))
        .flatMap((group) => [
          {
            group,
            polygons: group.groundCutPolygons ?? [],
            roles: undefined as string[] | undefined,
            sourceFids: undefined as number[] | undefined,
          },
          ...(group.surfaceCuts ?? []).map((cut) => ({
            group,
            sourceFids: undefined as number[] | undefined,
            ...cut,
          })),
          ...(group.sourceSurfaceCuts ?? []).map((cut) => ({
            group,
            roles: undefined as string[] | undefined,
            ...cut,
          })),
        ]),
      { group: undefined, polygons: waterPolygons ?? [], roles: undefined, sourceFids: undefined },
    ])
      for (const polygon of snap ? snapped(entry.polygons) : entry.polygons) {
        const b = bounds([polygon]),
          cut = {
            polygon,
            bounds: b,
            group: entry.group,
            roles: entry.roles,
            sourceFids: entry.sourceFids,
          };
        for (let x = Math.floor(b[0] / CELL); x <= Math.floor(b[2] / CELL); x++)
          for (let y = Math.floor(b[1] / CELL); y <= Math.floor(b[3] / CELL); y++) {
            const key = x + ',' + y;
            if (!this.cells.has(key)) this.cells.set(key, []);
            this.cells.get(key)!.push(cut);
          }
      }
  }
  private nearby(b: number[]) {
    const found = new Set<Cut>();
    for (let x = Math.floor(b[0] / CELL); x <= Math.floor(b[2] / CELL); x++)
      for (let y = Math.floor(b[1] / CELL); y <= Math.floor(b[3] / CELL); y++)
        for (const cut of this.cells.get(x + ',' + y) ?? [])
          if (
            cut.bounds[0] <= b[2] &&
            cut.bounds[2] >= b[0] &&
            cut.bounds[1] <= b[3] &&
            cut.bounds[3] >= b[1]
          )
            found.add(cut);
    return [...found];
  }
  at(point: readonly [number, number]): NativeBridgeGroup[] {
    return [
      ...new Set(
        this.nearby([point[0], point[1], point[0], point[1]])
          .filter((c) => !c.sourceFids && withinBridge(point, [c.polygon]))
          .flatMap((c) => (c.group ? [c.group] : []))
      ),
    ];
  }
  contains(point: readonly [number, number]) {
    return this.nearby([point[0], point[1], point[0], point[1]]).some(
      (c) =>
        !c.roles &&
        !c.sourceFids &&
        (!this.sourceWater || !c.group) &&
        withinBridge(point, [c.polygon])
    );
  }
  private owns(cut: Cut, role?: string, fid?: number) {
    if (cut.sourceFids) return fid !== undefined && cut.sourceFids.includes(fid);
    return cut.roles ? !role || cut.roles.includes(role) : !this.sourceWater || !cut.group;
  }
  surface(polygons: Polygons, role?: string, fid?: number): Polygons {
    const cuts = this.nearby(bounds(polygons))
      .filter((c) => this.owns(c, role, fid))
      .map((c) => c.polygon);
    if (!cuts.length) return polygons;
    const [x, y] = bounds(polygons);
    // 교차점 오차가 큰 절대 좌표 대신 해당 면 기준 1mm 정수 격자에서 표시 차집합을 계산한다.
    const local = (shape: Polygons): Polygons =>
      shape.map((p) =>
        p.map((r) => r.map((q) => [Math.round((q[0] - x) * 1000), Math.round((q[1] - y) * 1000)]))
      );
    const result = polygonClipping.difference(local(polygons), local(cuts)) as Polygons;
    return result.map((p) => p.map((r) => r.map((q) => [q[0] / 1000 + x, q[1] / 1000 + y])));
  }
  line(points: Point[], inside = false, role?: string): Point[][] {
    const nearby = this.nearby(bounds([[points]]));
    const cuts = nearby.filter((c) => this.owns(c, role)).map((c) => c.polygon);
    if (!cuts.length) return inside ? [] : [points];
    const boundaries = inside
      ? [
          ...cuts,
          ...[...new Set(nearby.flatMap((c) => (c.group ? [c.group] : [])))].flatMap((g) => [
            ...g.polygons,
            ...(g.sidewalks ?? []).flatMap((s) => s.polygons),
            ...g.profiles.flatMap((p) => p.polygons),
          ]),
        ]
      : cuts;
    const result: Point[][] = [];
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1],
        b = points[i],
        dx = b[0] - a[0],
        dy = b[1] - a[1],
        cutsAt = [0, 1];
      for (const polygon of boundaries)
        for (const ring of polygon)
          for (let j = 1; j < ring.length; j++) {
            const c = ring[j - 1],
              d = ring[j],
              ex = d[0] - c[0],
              ey = d[1] - c[1],
              den = dx * ey - dy * ex;
            if (Math.abs(den) < 1e-12) continue;
            const t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den,
              u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den;
            if (t > 0 && t < 1 && u >= 0 && u <= 1) cutsAt.push(t);
          }
      cutsAt.sort((x, y) => x - y);
      for (let j = 1; j < cutsAt.length; j++) {
        const lo = cutsAt[j - 1],
          hi = cutsAt[j],
          mid = (lo + hi) / 2;
        if (hi - lo < 1e-9 || withinBridge([a[0] + dx * mid, a[1] + dy * mid], cuts) !== inside)
          continue;
        result.push([
          [a[0] + dx * lo, a[1] + dy * lo],
          [a[0] + dx * hi, a[1] + dy * hi],
        ]);
      }
    }
    return result;
  }
}
