export function displayPoint(point: readonly number[], origin: readonly number[]) {
  // OSM 프리뷰와 같은 근거리 화면 투영. 수문 면적·경사 산정에 사용하지 않는다.
  return [
    (point[0] - origin[0]) * 111320 * Math.cos((origin[1] * Math.PI) / 180),
    -(point[1] - origin[1]) * 111320,
  ];
}
