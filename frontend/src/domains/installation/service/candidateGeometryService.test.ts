import { expect, test } from 'vitest';
import { candidateGeometry } from './candidateGeometryService';
import {
  candidateSurfaceLift,
  mergeCandidateParts,
  nearbyCandidateTiles,
  type GroundCandidate,
} from './candidateTilesService';
import { areaLift } from '../../topography/service/structureGeometryService';
import { buildingRaycast } from '../../city/service/buildingRaycastService';
import { BufferAttribute, BufferGeometry, Mesh, Raycaster, Vector3 } from 'three';
const polygon = (a: number, b: number): [number, number][][][] => [
  [
    [
      [a, 0],
      [b, 0],
      [b, 10],
      [a, 10],
      [a, 0],
    ],
  ],
];
test('후보는 모든 도로·보도 면 위에서 같은 후보 식별자로 선택', () => {
  const row: GroundCandidate = ['C' + 'a'.repeat(24), '11200', 2, polygon(0, 10)];
  const data = candidateGeometry([row], null);
  for (const layer of ['N1A_A0010000', 'N3A_A0010000', 'N1A_A0033320', 'N1A_A0080000'])
    expect(candidateSurfaceLift).toBeGreaterThan(areaLift(layer));
  for (let i = 1; i < data.positions.length; i += 3)
    expect(data.positions[i]).toBeCloseTo(candidateSurfaceLift);
  expect([...new Set(data.masks)]).toEqual([2]);
  const geometry = new BufferGeometry().setAttribute(
    'position',
    new BufferAttribute(data.positions, 3)
  );
  const mesh = new Mesh(geometry);
  mesh.raycast = buildingRaycast(data);
  const ray = new Raycaster(new Vector3(5, 50, -5), new Vector3(0, -1, 0));
  expect(ray.intersectObject(mesh).length).toBeGreaterThan(0);
  geometry.dispose();
});
test('타일 경계의 동일 후보를 합치며 2천 건 초과·기존 거리 제한에서도 누락하지 않음', () => {
  const row: GroundCandidate = ['C' + 'a'.repeat(24), '11200', 2, polygon(0, 10)];
  const other: GroundCandidate = [row[0], row[1], row[2], polygon(10, 20)];
  const before = structuredClone([row, other]);
  const merged = mergeCandidateParts([[row], [other]]);
  expect(merged).toHaveLength(1);
  expect(merged[0][3]).toHaveLength(2);
  expect([row, other]).toEqual(before);
  const rows = Array.from({ length: 2500 }, (_, i): GroundCandidate => [
    'C' + i.toString(16).padStart(24, '0'),
    '11200',
    2,
    polygon(i, i + 1),
  ]);
  expect(mergeCandidateParts([rows])).toHaveLength(2500);
  const tiles = [{ id: '0_0', bounds: [0, 0, 1000, 1000] }];
  expect(nearbyCandidateTiles(tiles, [0, 0], 4500)).toEqual(tiles);
  expect(nearbyCandidateTiles(tiles, [NaN, 0], 4500)).toEqual([]);
});
