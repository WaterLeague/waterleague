import type { WatershedLayout } from '../dto/watershedLayoutDto';
export type Point = [number, number];
export function layoutExtent(points: Point[]) {
  const xs = points.map((p) => p[0]),
    ys = points.map((p) => p[1]);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const pad = Math.max(maxX - minX, maxY - minY, 1) * 0.08;
  return {
    x: minX - pad,
    y: -maxY - pad,
    width: maxX - minX + 2 * pad,
    height: maxY - minY + 2 * pad,
  };
}
export function layoutLabel(points: Point[]): Point {
  // 큰 원 좌표의 곱셈 오차를 줄이도록 첫 꼭짓점을 기준으로 면적 중심을 계산한다.
  const [ox, oy] = points[0];
  let twiceArea = 0,
    x = 0,
    y = 0;
  points.forEach((p, i) => {
    const q = points[(i + 1) % points.length];
    const ax = p[0] - ox,
      ay = p[1] - oy,
      bx = q[0] - ox,
      by = q[1] - oy,
      cross = ax * by - bx * ay;
    twiceArea += cross;
    x += (ax + bx) * cross;
    y += (ay + by) * cross;
  });
  return Math.abs(twiceArea) > 1e-8
    ? [ox + x / (3 * twiceArea), oy + y / (3 * twiceArea)]
    : points[0];
}
export function downstreamLayout(layout: WatershedLayout, catchmentId: string) {
  const start = layout.catchments.find((c) => c.id === catchmentId)?.outletNodeId;
  const nodes = new Set<string>(),
    links = new Set<string>();
  if (start) nodes.add(start);
  const pending = start ? [start] : [];
  while (pending.length) {
    const node = pending.pop();
    for (const link of layout.links.filter((l) => l.fromNode === node)) {
      links.add(link.id);
      if (!nodes.has(link.toNode)) {
        nodes.add(link.toNode);
        pending.push(link.toNode);
      }
    }
  }
  return {
    start,
    nodes,
    links,
    outfalls: layout.nodes.filter((n) => n.kind === 'OUTFALL' && nodes.has(n.id)).map((n) => n.id),
  };
}
