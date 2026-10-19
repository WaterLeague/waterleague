import { Color, ShapeGeometry } from 'three';
import type { MapPolygons } from '../../catalog/service/mapGeometryService';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';

type Point = [number, number];
type Triangle = [Point, Point, Point];
export function riverGeometry(surfaces: MapPolygons[], terrain: Terrain | null) {
  const triangles: Triangle[] = [];
  for (const polygons of surfaces) {
    const shape = new ShapeGeometry(polygonShapes(polygons));
    const points = shape.getAttribute('position');
    const indices = shape.getIndex();
    if (indices)
      for (let i = 0; i < indices.count; i += 3)
        triangles.push(
          [0, 1, 2].map((j) => {
            const index = indices.getX(i + j);
            return [points.getX(index), points.getY(index)];
          }) as Triangle
        );
    shape.dispose();
  }
  let planned = triangles.length;
  const positions: number[] = [];
  // 원 물 경계와 구멍을 유지한 삼각형 내부 분할로 긴 수면의 물결을 표현한다.
  const subdivide = ([a, b, c]: Triangle, level = 0) => {
    const ab = Math.hypot(a[0] - b[0], a[1] - b[1]);
    const bc = Math.hypot(b[0] - c[0], b[1] - c[1]);
    const ca = Math.hypot(c[0] - a[0], c[1] - a[1]);
    if (Math.max(ab, bc, ca) > 80 && level < 14 && planned < 120000) {
      planned++;
      const [p, q, other] = ab >= bc && ab >= ca ? [a, b, c] : bc >= ca ? [b, c, a] : [c, a, b];
      const middle: Point = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      subdivide([p, middle, other], level + 1);
      subdivide([middle, q, other], level + 1);
    } else {
      for (const p of [a, b, c]) positions.push(p[0], terrainHeight(terrain, p) + 2, -p[1]);
    }
  };
  triangles.forEach((triangle) => subdivide(triangle));
  const count = positions.length / 3;
  const colors = new Float32Array(positions.length),
    color = new Color('#287b91');
  for (let i = 0; i < count; i++) colors.set(color.toArray(), i * 3);
  return {
    positions: new Float32Array(positions),
    colors,
    flows: new Float32Array(count * 2),
    depths: new Float32Array(count),
    faces: new Float32Array(count).fill(1),
  };
}
