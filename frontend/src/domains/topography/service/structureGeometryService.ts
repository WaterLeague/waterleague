import { Color } from 'three';
import type { Terrain } from '../../terrain/entity/terrain';
import { drapeSegment, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import { streetOffsets } from '../../urban/service/streetGeometryService';
type Point = [number, number];
type Vertex = [number, number, number];
export function structureWriter(
  positions: number[],
  colors: number[],
  terrain: Terrain | null,
  height: (point: readonly [number, number]) => number = (point) =>
    terrainMeshHeight(terrain, point)
) {
  const triangle = (a: Vertex, b: Vertex, c: Vertex, color: Color) => {
    for (const p of [a, b, c]) {
      positions.push(...p);
      colors.push(color.r, color.g, color.b);
    }
  };
  const quad = (a: Vertex, b: Vertex, c: Vertex, d: Vertex, color: Color) => {
    triangle(a, b, c, color);
    triangle(a, c, d, color);
  };
  const vertex = (p: readonly [number, number], lift: number): Vertex => [
    p[0],
    height(p) + lift,
    -p[1],
  ];
  const beam = (
    a: readonly [number, number],
    b: readonly [number, number],
    bottom: number,
    beamHeight: number,
    width: number,
    color: Color
  ) => {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 1e-5) return;
    const dx = ((-(b[1] - a[1]) / len) * width) / 2,
      dy = (((b[0] - a[0]) / len) * width) / 2;
    const al: Point = [a[0] + dx, a[1] + dy],
      ar: Point = [a[0] - dx, a[1] - dy],
      bl: Point = [b[0] + dx, b[1] + dy],
      br: Point = [b[0] - dx, b[1] - dy];
    // 부재 양쪽 모서리는 중심선 높이를 공유해 상판 경계에서 한쪽만 지면으로 꺾이지 않게 한다.
    const ha = height(a),
      hb = height(b);
    const at = (p: Point, base: number, lift: number): Vertex => [p[0], base + lift, -p[1]];
    const v = [
      at(al, ha, bottom),
      at(ar, ha, bottom),
      at(br, hb, bottom),
      at(bl, hb, bottom),
      at(al, ha, bottom + beamHeight),
      at(ar, ha, bottom + beamHeight),
      at(br, hb, bottom + beamHeight),
      at(bl, hb, bottom + beamHeight),
    ];
    for (const [i, j, k, l] of [
      [0, 1, 5, 4],
      [1, 2, 6, 5],
      [2, 3, 7, 6],
      [3, 0, 4, 7],
      [4, 5, 6, 7],
      [3, 2, 1, 0],
    ])
      quad(v[i], v[j], v[k], v[l], color);
  };
  const line = (id: string, part: Point[], color: Color) => {
    const code = id.slice(4, 8);
    if (code === 'A012' || code === 'C046') {
      const first = part[0],
        last = part.at(-1)!;
      // 입구 원 선형 위에 문틀을 세우고 통행 공간은 비워 둔다.
      const clearance = code === 'A012' ? 4.8 : 2.6;
      for (let i = 1; i < part.length; i++) beam(part[i - 1], part[i], clearance, 0.5, 0.6, color);
      for (const p of [first, last]) beam(p, [p[0] + 0.1, p[1]], 0, clearance, 0.6, color);
      return true;
    }
    if (code === 'C008') {
      for (let i = 1; i < part.length; i++) {
        for (const [a, b] of drapeSegment(part[i - 1], part[i], terrain))
          beam(a, b, 0.8, 0.25, 2.4, color);
        const a = part[i - 1],
          b = part[i],
          length = Math.hypot(b[0] - a[0], b[1] - a[1]);
        for (let s = 0; s < length; s += 8) {
          const p: Point = [
            a[0] + ((b[0] - a[0]) * s) / length,
            a[1] + ((b[1] - a[1]) * s) / length,
          ];
          beam(p, [p[0] + 0.1, p[1]], 0, 0.8, 0.3, color);
        }
      }
      return true;
    }
    if (code === 'A002' || code === 'A003') {
      const width = code === 'A003' ? 1.8 : 2.8;
      const left = streetOffsets(part, -width / 2),
        right = streetOffsets(part, width / 2);
      const surface = new Color(code === 'A003' ? '#b3ae9f' : '#667071');
      for (let i = 1; i < part.length; i++) {
        // 폭 미확인 선형은 표시용 폭으로 입체화하며 후보 면적에는 사용하지 않는다.
        const length = Math.hypot(part[i][0] - part[i - 1][0], part[i][1] - part[i - 1][1]);
        const steps = Math.max(1, Math.ceil(length / 20));
        const at = (line: Point[], t: number): Point => [
          line[i - 1][0] + (line[i][0] - line[i - 1][0]) * t,
          line[i - 1][1] + (line[i][1] - line[i - 1][1]) * t,
        ];
        for (let j = 0; j < steps; j++)
          quad(
            vertex(at(left, j / steps), 0.022),
            vertex(at(right, j / steps), 0.022),
            vertex(at(right, (j + 1) / steps), 0.022),
            vertex(at(left, (j + 1) / steps), 0.022),
            surface
          );
      }
      return true;
    }
    const rail = code === 'A015' || code === 'A017';
    const wall = [
      'B002',
      'C005',
      'C006',
      'C007',
      'C032',
      'C052',
      'C053',
      'E006',
      'F003',
      'F004',
    ].includes(code);
    if (!rail && !wall) return false;
    const paths = rail ? [streetOffsets(part, -0.7175), streetOffsets(part, 0.7175)] : [part];
    for (const path of paths)
      for (let i = 1; i < path.length; i++)
        for (const [a, b] of drapeSegment(path[i - 1], path[i], terrain)) {
          if (rail) beam(a, b, 0.16, 0.16, 0.085, color);
          else if (code === 'C053') {
            beam(a, b, 0.5, 0.1, 0.08, color);
            beam(a, b, 1, 0.1, 0.08, color);
            const distance = Math.hypot(b[0] - a[0], b[1] - a[1]);
            for (let s = 0; s < distance; s += 3) {
              const p: Point = [
                a[0] + ((b[0] - a[0]) * s) / distance,
                a[1] + ((b[1] - a[1]) * s) / distance,
              ];
              beam(p, [p[0] + 0.08, p[1]], 0.02, 1.1, 0.08, color);
            }
          } else if (code === 'E006') {
            for (const side of [-1, 1]) {
              const edge = streetOffsets(
                [
                  [a[0], a[1]],
                  [b[0], b[1]],
                ],
                side * 0.45
              );
              beam(edge[0], edge[1], 0, 0.28, 0.12, color);
            }
            beam(a, b, 0.01, 0.03, 0.75, new Color('#79a3ad'));
          } else
            beam(
              a,
              b,
              0,
              code === 'C052' ? 0.55 : code === 'F004' ? 1.5 : 1.1,
              code === 'C005' ? 1 : 0.22,
              color
            );
        }
    if (rail)
      for (let i = 1; i < part.length; i++) {
        const a = part[i - 1],
          b = part[i],
          len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        for (let s = 0; s < len; s += 2.4) {
          const p: Point = [a[0] + ((b[0] - a[0]) * s) / len, a[1] + ((b[1] - a[1]) * s) / len],
            d: Point = [(-(b[1] - a[1]) / len) * 1.05, ((b[0] - a[0]) / len) * 1.05];
          beam(
            [p[0] - d[0], p[1] - d[1]],
            [p[0] + d[0], p[1] + d[1]],
            0.04,
            0.12,
            0.2,
            new Color('#8b8a7b')
          );
        }
      }
    return true;
  };
  const sides = (polygon: Point[][], lift: number, color: Color, bottom = 0) => {
    for (const ring of polygon)
      for (let i = 1; i < ring.length; i++)
        for (const [a, b] of drapeSegment(ring[i - 1], ring[i], terrain))
          quad(vertex(a, bottom), vertex(b, bottom), vertex(b, lift), vertex(a, lift), color);
  };
  return { triangle, quad, vertex, beam, line, sides };
}
export function areaLift(id: string) {
  const code = id.slice(4, 8);
  // 겹치는 지표 종류에 일정한 높이 순서를 부여해 같은 깊이의 면 충돌을 피한다.
  if (code === 'D001') return 0.008;
  if (code === 'A001') return id.startsWith('N3') ? 0.012 : 0.016;
  if (code === 'A008' || code === 'A009' || code === 'A010') return 0.016;
  if (code === 'A011') return 0.036;
  if (code === 'A016') return 0.046;
  if (code === 'C017' || code === 'C018') return 2.4;
  if (code === 'C047') return 1.2;
  if (code === 'A019') return 0.65;
  if (code === 'A020') return 4.2;
  if (code === 'A003') return 0.14;
  if (code === 'B001') return 0.2;
  if (code === 'C003') return 0.35;
  return 0.055;
}
