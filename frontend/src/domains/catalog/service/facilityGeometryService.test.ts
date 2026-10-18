import { placementFootprint } from './facilityGeometryService';
import model from '../../../../../data/models/seongsu-lab.json';
import { describe, expect, it } from 'vitest';
import { facilityFootprint, plantingMarkers, polygonArea } from './facilityGeometryService';
import type { MapPoint } from '../entity/facilityFootprint';
import { CatalogError } from '../exception/CatalogError';

const concave: MapPoint[] = [
  [0, 0],
  [12, 0],
  [12, 12],
  [8, 12],
  [8, 4],
  [4, 4],
  [4, 12],
  [0, 12],
  [0, 0],
];
function contains(ring: MapPoint[], [x, y]: MapPoint) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, ay] = ring[i],
      [bx, by] = ring[j];
    const cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax);
    if (
      Math.abs(cross) < 1e-6 &&
      x >= Math.min(ax, bx) - 1e-8 &&
      x <= Math.max(ax, bx) + 1e-8 &&
      y >= Math.min(ay, by) - 1e-8 &&
      y <= Math.max(ay, by) + 1e-8
    )
      return true;
    if (ay > y !== by > y && x < ((bx - ax) * (y - ay)) / (by - ay) + ax) inside = !inside;
  }
  return inside;
}

describe('시설 표시 경계', () => {
  it('오목한 구역과 분리된 절단면에서 면적 비율·내포·원본을 보존한다', () => {
    const before = structuredClone(concave);
    for (const ring of [
      concave,
      [...concave].reverse(),
      concave.map(([x, y]): MapPoint => [y, x]),
    ]) {
      for (const ratio of [0.0001, 0.1, 0.5, 0.75, 1]) {
        const footprint = facilityFootprint(ring, ratio);
        expect(footprint.area).toBeCloseTo(polygonArea(ring) * ratio, 7);
        expect(footprint).toEqual(facilityFootprint(ring, ratio));
        for (const piece of footprint.polygons) {
          for (let i = 0; i < piece.length; i++) {
            const a = piece[i],
              b = piece[(i + 1) % piece.length];
            for (const t of [0, 0.25, 0.5, 0.75, 1])
              expect(contains(ring, [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])).toBe(
                true
              );
          }
        }
      }
    }
    expect(concave).toEqual(before);
  });

  it('내부 삼각선은 제외하고 전체 외곽 길이를 보존한다', () => {
    const footprint = facilityFootprint(concave, 1);
    const length = footprint.boundary.reduce(
      (sum, [a, b]) => sum + Math.hypot(a[0] - b[0], a[1] - b[1]),
      0
    );
    expect(length).toBeCloseTo(64, 8);
    expect(footprint.boundary).toHaveLength(8);
  });

  it('실제 성수 13개 구역의 작은 면적·최대 면적을 같은 비율로 표시한다', () => {
    expect(model.cells).toHaveLength(13);
    for (const cell of model.cells)
      for (const area of [0.01, Math.min(40, cell.maxAreaM2), cell.maxAreaM2]) {
        const footprint = facilityFootprint(cell.coordinates as MapPoint[], area / cell.areaM2);
        expect(footprint.area / polygonArea(cell.coordinates as MapPoint[])).toBeCloseTo(
          area / cell.areaM2,
          8
        );
        for (const point of footprint.polygons.flat())
          expect(contains(cell.coordinates as MapPoint[], point)).toBe(true);
      }
  });

  it('도식 식재를 경계 안에 제한하고 결정적으로 생성한다', () => {
    const footprint = facilityFootprint(concave, 0.9);
    const markers = plantingMarkers(footprint, 16);
    expect(markers.length).toBeGreaterThan(0);
    expect(markers.length).toBeLessThanOrEqual(16);
    expect(markers).toEqual(plantingMarkers(footprint, 16));
    for (const point of markers) expect(contains(concave, point)).toBe(true);
    expect(() => plantingMarkers(footprint, 100000)).toThrow(CatalogError);
  });

  it('자기교차·퇴화·비유한 좌표와 면적 범위 위반을 거부한다', () => {
    for (const ratio of [0, -1, 1.01, NaN, Infinity, 1e-300])
      expect(() => facilityFootprint(concave, ratio)).toThrow(CatalogError);
    const invalid: MapPoint[][] = [
      [],
      [
        [0, 0],
        [1, 0],
        [2, 0],
      ],
      [
        [0, 0],
        [1, 0],
        [1, 1],
        [NaN, 1],
      ],
      [
        [0, 0],
        [2, 2],
        [0, 2],
        [2, 0],
      ],
      [
        [0, 0],
        [2, 0],
        [2, 0],
        [0, 2],
      ],
      [
        [0, 0],
        [4, 0],
        [0, 3],
        [3, 3],
        [1, -1],
      ],
    ];
    for (const ring of invalid) expect(() => facilityFootprint(ring, 0.5)).toThrow(CatalogError);
  });
});

it('식생수로는 설치 면적이 작아져도 폭 2m 유지와 길이만 축소', () => {
  const swaleDesign = {
    method: 'CONTAINED_FIXED_WIDTH_STRAIGHT_DESIGN_V1' as const,
    topWidthM: 2 as const,
    maxLengthM: 5,
    maxAreaM2: 10,
    center: [0, 0] as [number, number],
    direction: [1, 0] as [number, number],
    coordinates: [
      [-2.5, -1],
      [2.5, -1],
      [2.5, 1],
      [-2.5, 1],
      [-2.5, -1],
    ] as [number, number][],
    slopeBasis: 'REGIONAL_TERRAIN_PROXY_NOT_LONGITUDINAL_SURVEY' as const,
    outlet: 'SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK' as const,
  };
  const cell = {
    coordinates: [
      [-3, -3],
      [3, -3],
      [3, 3],
      [-3, 3],
    ] as [number, number][],
    areaM2: 36,
    physicalInputs: { swaleDesign },
  };
  const p = { cellId: 'G1', facilityType: 'VEGETATIVE_SWALE' as const, areaM2: 4 };
  const shape = placementFootprint(cell, p);
  expect(shape.area).toBeCloseTo(4);
  expect(Math.max(...shape.polygons.flat().map((p) => p[1]))).toBe(1);
  expect(Math.min(...shape.polygons.flat().map((p) => p[1]))).toBe(-1);
  expect(() => placementFootprint(cell, { ...p, areaM2: 10.01 })).toThrow();
});
