type Point = [number, number];
type Polygons = Point[][][];
export function bridgeAxis(polygons: Polygons): Point {
  const points = polygons.flatMap((p) => p[0]);
  const center = points.reduce(
    (sum, p) => [sum[0] + p[0] / points.length, sum[1] + p[1] / points.length],
    [0, 0]
  );
  let xx = 0,
    xy = 0,
    yy = 0;
  for (const p of points) {
    const x = p[0] - center[0],
      y = p[1] - center[1];
    xx += x * x;
    xy += x * y;
    yy += y * y;
  }
  const angle = Math.atan2(2 * xy, xx - yy) / 2;
  return [Math.cos(angle), Math.sin(angle)];
}
export function bridgePierPositions(polygons: Polygons, edges = false): Point[] {
  const axis = bridgeAxis(polygons),
    normal: Point = [-axis[1], axis[0]];
  const along = (p: Point) => p[0] * axis[0] + p[1] * axis[1];
  const across = (p: Point) => p[0] * normal[0] + p[1] * normal[1];
  const projection = polygons.flatMap((p) => p[0].map(along));
  const start = Math.min(...projection),
    end = Math.max(...projection);
  const points: Point[] = [];
  // 경사·곡선 상판의 실제 단면 안에만 표시용 교각을 배치한다.
  for (let station = start + 20; station < end - 15; station += 60) {
    const intervals: [number, number][] = [];
    for (const polygon of polygons) {
      const crossings: number[] = [];
      for (const ring of polygon)
        for (let i = 1; i < ring.length; i++) {
          const a = ring[i - 1],
            b = ring[i],
            x = along(a),
            y = along(b);
          if ((x <= station && y > station) || (y <= station && x > station)) {
            const t = (station - x) / (y - x);
            crossings.push(across(a) + t * (across(b) - across(a)));
          }
        }
      crossings.sort((a, b) => a - b);
      for (let i = 0; i + 1 < crossings.length; i += 2)
        intervals.push([crossings[i], crossings[i + 1]]);
    }
    intervals.sort((a, b) => a[0] - b[0]);
    const merged: [number, number][] = [];
    for (const interval of intervals) {
      const last = merged.at(-1);
      if (last && interval[0] <= last[1] + 1e-7) last[1] = Math.max(last[1], interval[1]);
      else merged.push([...interval]);
    }
    for (const [a, b] of merged)
      if (b - a >= 2) {
        // 복층 상판의 지지대가 하층 통행면 중앙을 관통하지 않도록 양옆에 둔다.
        for (const lateral of edges && b - a > 4 ? [a + 1, b - 1] : [(a + b) / 2])
          points.push([
            axis[0] * station + normal[0] * lateral,
            axis[1] * station + normal[1] * lateral,
          ]);
      }
  }
  return points;
}
