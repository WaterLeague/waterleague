type Point = [number, number];

export function positionPlanLabels(
  centers: Point[],
  scale: number,
  width: number,
  height: number
): Point[] {
  const labelWidth = 36 / scale;
  const labelHeight = 28 / scale;
  const placed: Point[] = [];
  for (const [x, y] of centers) {
    const candidates: Point[] = [[x, y]];
    for (let ring = 1; ring <= 6; ring++) {
      candidates.push([x, y - labelHeight * ring], [x, y + labelHeight * ring]);
      for (let step = -ring; step <= ring; step++) {
        candidates.push(
          [x - labelWidth * ring, y + labelHeight * step],
          [x + labelWidth * ring, y + labelHeight * step]
        );
      }
    }
    const position = candidates.find(
      ([east, north]) =>
        Math.abs(east) + labelWidth / 2 <= width / 2 &&
        Math.abs(north) + labelHeight / 2 <= height / 2 &&
        placed.every(
          ([otherEast, otherNorth]) =>
            Math.abs(east - otherEast) >= labelWidth || Math.abs(north - otherNorth) >= labelHeight
        )
    );
    placed.push(position ?? [x, y]);
  }
  return placed;
}
