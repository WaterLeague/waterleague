import { expect, test } from 'vitest';
import { pavementGeometry } from './pavementGeometryService';
import { placementFootprint } from './facilityGeometryService';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import type { Terrain } from '../../terrain/entity/terrain';
import {
  BufferAttribute,
  BufferGeometry,
  DoubleSide,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
} from 'three';
import { candidateGeometry } from '../../installation/service/candidateGeometryService';
import { streetGeometry } from '../../urban/service/streetGeometryService';
import type { Street } from '../../urban/entity/urban';
import { surfaceGeometry } from '../../surface/service/surfaceGeometry';
import type { SurfaceFrame } from '../../surface/entity/surface';
import { pavementSurfaceLift } from '../../terrain/service/surfaceDisplayService';

const terrain: Terrain = {
  width: 3,
  height: 3,
  origin: [0, 20],
  spacing: [10, -10],
  heights: new Float32Array([0, 12, 0, 0, 0, 10, 5, 0, 0]),
  cover: new Uint8Array(9),
  districts: new Uint8Array(9),
  districtIds: [],
};

test('도로 투수포장 면적 보존과 경사면 부착', () => {
  const cell = {
    coordinates: [
      [1, 19],
      [19, 19],
      [19, 17],
      [1, 17],
      [1, 19],
    ] as [number, number][],
    areaM2: 36,
    heightM: 0,
  };
  const footprint = placementFootprint(cell, {
    cellId: 'ROAD',
    facilityType: 'PERMEABLE_PAVEMENT',
    areaM2: 20,
  });
  const geometry = pavementGeometry(footprint, terrain);
  const positions = geometry.surface.getAttribute('position');
  let area = 0;
  for (let i = 0; i < positions.count; i += 3) {
    const triangle = [i, i + 1, i + 2].map(
      (index) => [positions.getX(index), -positions.getZ(index)] as const
    );
    const height = [i, i + 1, i + 2].reduce((n, index) => n + positions.getY(index), 0) / 3;
    const center: [number, number] = [
      triangle.reduce((n, p) => n + p[0], 0) / 3,
      triangle.reduce((n, p) => n + p[1], 0) / 3,
    ];
    expect(height - terrainMeshHeight(terrain, center)).toBeCloseTo(pavementSurfaceLift, 5);
    const [a, b, c] = triangle;
    area += Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2;
  }
  expect(area).toBeCloseTo(20, 4);
  Object.values(geometry).forEach((g) => g.dispose());
});

test.each(['ROAD_AREA', 'SIDEWALK_AREA'])(
  '%s에서 후보보다 포장이 앞에 놓이며 구멍·상부 교량·1mm 침수 가림 보존',
  (nativeSourceRole) => {
    const polygons: [number, number][][][] = [
      [
        [
          [0, 0],
          [20, 0],
          [20, 20],
          [0, 20],
          [0, 0],
        ],
        [
          [8, 8],
          [8, 12],
          [12, 12],
          [12, 8],
          [8, 8],
        ],
      ],
    ];
    const road: Street = {
      id: 'test-road',
      class: 'service',
      districtId: '11200',
      widthM: 20,
      widthSource: 'NOT_CONFIRMED',
      nativeSourceRole,
      nativePolygons: polygons,
      walk: true,
      motor: false,
      oneway: 0,
      sidewalk: 'unknown',
      bridge: false,
      coordinates: [
        [0, 10],
        [20, 10],
      ],
    };
    const cell = { polygons, areaM2: 384, heightM: 0 };
    const placement = {
      cellId: 'test-road',
      facilityType: 'PERMEABLE_PAVEMENT' as const,
      areaM2: 384,
    };
    const before = JSON.stringify({ road, cell, placement });
    const pavement = pavementGeometry(placementFootprint(cell, placement), terrain);
    const material = new MeshBasicMaterial({ side: DoubleSide });
    const geometries: BufferGeometry[] = [];
    const mesh = (positions: Float32Array) => {
      const geometry = new BufferGeometry().setAttribute(
        'position',
        new BufferAttribute(positions, 3)
      );
      geometries.push(geometry);
      return new Mesh(geometry, material);
    };
    const street = mesh(streetGeometry([road], terrain, false).positions);
    const candidate = mesh(
      candidateGeometry([['test-road', '11200', 2, polygons]], terrain).positions
    );
    const facilityMaterial = new MeshBasicMaterial();
    const facility = new Mesh(pavement.surface, facilityMaterial);
    const bridge = mesh(streetGeometry([{ ...road, bridge: true }], terrain, false).positions);
    const frame = {
      cells: [
        {
          triangleId: 0,
          vertices: [
            [0, 0],
            [20, 0],
            [20, 20],
          ],
          depthM: 0.001,
          speedMps: 0.4,
          flowDirection: [1, 0],
        },
        {
          triangleId: 1,
          vertices: [
            [0, 0],
            [20, 20],
            [0, 20],
          ],
          depthM: 0.001,
          speedMps: 0.4,
          flowDirection: [1, 0],
        },
      ],
    } as SurfaceFrame;
    const frameBefore = JSON.stringify(frame);
    const water = mesh(surfaceGeometry(frame, 'depth', terrain).positions);
    for (const [east, north] of [
      [3, 15],
      [16, 4],
    ]) {
      const ray = new Raycaster(new Vector3(east, 100, -north), new Vector3(0, -1, 0));
      const layers = ray.intersectObjects([street, candidate, facility]);
      expect(layers[0].object).toBe(facility);
      const hit = (object: Mesh) => layers.find((item) => item.object === object)!.point.y;
      expect(hit(facility)).toBeGreaterThan(hit(candidate));
      expect(hit(candidate)).toBeGreaterThan(hit(street));
      expect(ray.intersectObjects([street, candidate, facility, bridge])[0].object).toBe(bridge);
      expect(ray.intersectObjects([street, candidate, facility, water])[0].object).toBe(water);
    }
    const hole = new Raycaster(new Vector3(10, 100, -10), new Vector3(0, -1, 0));
    expect(hole.intersectObjects([street, candidate, facility])).toHaveLength(0);
    expect(JSON.stringify({ road, cell, placement })).toBe(before);
    expect(JSON.stringify(frame)).toBe(frameBefore);
    geometries.forEach((geometry) => geometry.dispose());
    Object.values(pavement).forEach((geometry) => geometry.dispose());
    material.dispose();
    facilityMaterial.dispose();
  }
);
