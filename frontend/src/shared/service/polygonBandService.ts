type Point = [number, number];
// 삼각형을 계단 폭으로 잘라 원본 외곽·구멍을 보존한다.
export function stairTriangles(
  triangle: Point[],
  axis: Point,
  origin: number,
  step: number
): { points: Point[]; band: number }[] {
  const coordinate = (p: Point) => p[0] * axis[0] + p[1] * axis[1];
  const clip = (values: Point[], bound: number, above: boolean) => {
    const output: Point[] = [];
    for (let i = 0; i < values.length; i++) {
      const a = values[i],
        b = values[(i + 1) % values.length],
        da = coordinate(a) - bound,
        db = coordinate(b) - bound,
        ina = above ? da >= -1e-8 : da <= 1e-8,
        inb = above ? db >= -1e-8 : db <= 1e-8;
      if (ina) output.push(a);
      if (ina !== inb) {
        const t = da / (da - db);
        output.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    return output;
  };
  const values = triangle.map(coordinate),
    first = Math.floor((Math.min(...values) - origin) / step),
    last = Math.floor((Math.max(...values) - origin) / step),
    result = [];
  for (let band = first; band <= last; band++) {
    const points = clip(
      clip(triangle, origin + band * step, true),
      origin + (band + 1) * step,
      false
    );
    if (points.length >= 3) result.push({ points, band });
  }
  return result;
}
