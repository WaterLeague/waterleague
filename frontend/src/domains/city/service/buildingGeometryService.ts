import { ShapeUtils, Vector2 } from 'three';
import type { CityBuilding } from '../entity/city';

export type BuildingMeshData = {
  positions: Float32Array;
  normals: Float32Array;
  bounds: Float32Array;
  ends: number[];
};
export function buildingMeshCapacity(buildings: CityBuilding[]): number {
  const capacity =
    buildings.reduce(
      (sum, building) =>
        sum +
        building.polygons.reduce(
          (n, polygon) =>
            n +
            polygon.reduce((s, ring) => s + (ring.length - 1) * 12, 0) +
            (polygon.length - 2) * 12,
          0
        ),
      0
    ) * 3;
  if (capacity > 90000000) throw new Error('건물 표시 형상 상한 초과');
  return capacity;
}
export function buildBuildingMesh(buildings: CityBuilding[]): BuildingMeshData {
  // 건물마다 임시 형상을 만들지 않고 원 도형을 한 번 삼각분할해 전송 버퍼에 쓴다.
  const capacity = buildingMeshCapacity(buildings);
  const positions = new Float32Array(capacity),
    normals = new Float32Array(capacity);
  const ends: number[] = [],
    bounds = new Float32Array(buildings.length * 6);
  let offset = 0;
  const vertex = (p: Vector2, z: number, nx: number, ny: number, nz: number) => {
    positions.set([p.x, p.y, z], offset);
    normals.set([nx, ny, nz], offset);
    offset += 3;
  };
  for (const building of buildings) {
    const bottom = building.baseElevationM ?? 0,
      top = bottom + building.heightM;
    let minx = Infinity,
      miny = Infinity,
      maxx = -Infinity,
      maxy = -Infinity;
    for (const polygon of building.polygons) {
      const rings = polygon.map((ring) => ring.slice(0, -1).map(([x, y]) => new Vector2(x, y)));
      const points = rings.flat();
      for (const point of points) {
        minx = Math.min(minx, point.x);
        miny = Math.min(miny, point.y);
        maxx = Math.max(maxx, point.x);
        maxy = Math.max(maxy, point.y);
      }
      for (const ids of ShapeUtils.triangulateShape(rings[0], rings.slice(1))) {
        const [a, b, c] = ids.map((id) => points[id]);
        const forward =
          (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) >= 0 ? [a, b, c] : [a, c, b];
        for (const point of forward) vertex(point, top, 0, 0, 1);
        for (const point of [...forward].reverse()) vertex(point, bottom, 0, 0, -1);
      }
      for (const [index, ring] of rings.entries()) {
        const sign = (ShapeUtils.isClockWise(ring) ? -1 : 1) * (index ? -1 : 1);
        for (let i = 0; i < ring.length; i++) {
          const a = ring[i],
            b = ring[(i + 1) % ring.length],
            dx = b.x - a.x,
            dy = b.y - a.y;
          const length = Math.hypot(dx, dy);
          if (!length) continue;
          const nx = (sign * dy) / length,
            ny = (-sign * dx) / length;
          const face: [Vector2, number][] =
            sign > 0
              ? [
                  [a, bottom],
                  [b, bottom],
                  [a, top],
                  [a, top],
                  [b, bottom],
                  [b, top],
                ]
              : [
                  [b, bottom],
                  [a, bottom],
                  [b, top],
                  [b, top],
                  [a, bottom],
                  [a, top],
                ];
          for (const [point, z] of face) vertex(point, z, nx, ny, 0);
        }
      }
    }
    bounds.set([minx, miny, bottom, maxx, maxy, top], ends.length * 6);
    ends.push(offset / 9);
  }
  return {
    positions: positions.subarray(0, offset),
    normals: normals.subarray(0, offset),
    bounds,
    ends,
  };
}
