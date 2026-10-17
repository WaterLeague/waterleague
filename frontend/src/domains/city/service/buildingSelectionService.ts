// 합쳐 그린 메시의 삼각형 번호를 원본 건물 순서로 되돌린다.
export function buildingFaceIndex(ends: number[], face: number): number {
  if (!Number.isInteger(face) || face < 0) return -1;
  let left = 0,
    right = ends.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (ends[middle] <= face) left = middle + 1;
    else right = middle;
  }
  return left < ends.length ? left : -1;
}

export function inBuildingRing([x, y]: [number, number], ring: [number, number][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [a, b] = ring[i],
      [c, d] = ring[j];
    if (b > y !== d > y && x < ((c - a) * (y - b)) / (d - b) + a) inside = !inside;
  }
  return inside;
}
