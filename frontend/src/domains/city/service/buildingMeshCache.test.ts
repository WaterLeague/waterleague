import { expect, test } from 'vitest';
import { BuildingMeshCache, buildingMeshKey } from './buildingMeshCache';
import { buildBuildingMesh } from './buildingGeometryService';
import type { CityBuilding } from '../entity/city';

const building: CityBuilding = {
  id: 'ngii:N1A_B0010000:' + '1'.repeat(64),
  heightM: 12,
  center: [15, 15],
  areaM2: 900,
  heightSource: 'FLOOR_COUNT_DISPLAY_ASSUMPTION',
  districtId: '11200',
  candidateId: null,
  geometryEligibility: 'GEOMETRY_ONLY',
  polygons: [
    [
      [
        [0, 0],
        [30, 0],
        [30, 30],
        [0, 30],
        [0, 0],
      ],
    ],
  ],
};

test('전환 후 같은 원본은 재사용하고 형상·높이·표고·순서 변경은 구분', () => {
  const cache = new BuildingMeshCache();
  const key = buildingMeshKey([building]);
  const mesh = buildBuildingMesh([building]);
  cache.put(key, mesh);
  expect(cache.get(buildingMeshKey(structuredClone([building])))).toBe(mesh);
  for (const changed of [
    { ...building, heightM: 13 },
    { ...building, baseElevationM: 3 },
    {
      ...building,
      polygons: [
        [
          [
            [0, 0],
            [31, 0],
            [30, 30],
            [0, 30],
            [0, 0],
          ],
        ],
      ],
    } as CityBuilding,
  ])
    expect(cache.get(buildingMeshKey([changed]))).toBeUndefined();
  const other = { ...building, id: 'ngii:N1A_B0010000:' + '2'.repeat(64), heightM: 20 };
  expect(buildingMeshKey([building, other])).not.toBe(buildingMeshKey([other, building]));
  expect(mesh).toEqual(buildBuildingMesh([building]));
});

test('메시·키 용량 상한과 최근 사용 순서·대형 메시 제외 적용', () => {
  const mesh = {
    positions: new Float32Array(9),
    normals: new Float32Array(9),
    bounds: new Float32Array(6),
    ends: [1],
  };
  const cache = new BuildingMeshCache(212);
  cache.put('a', mesh);
  cache.put('b', mesh);
  expect(cache.get('a')).toBe(mesh);
  cache.put('c', mesh);
  expect(cache.get('b')).toBeUndefined();
  expect(cache.get('a')).toBe(mesh);
  cache.put('large', { ...mesh, positions: new Float32Array(100) });
  expect(cache.get('large')).toBeUndefined();
  expect(cache.get('c')).toBe(mesh);
  cache.put('a', mesh);
  cache.put('d', mesh);
  expect(cache.get('c')).toBeUndefined();
  cache.clear();
  expect(cache.get('a')).toBeUndefined();
});

test('버퍼 일부 뷰도 원 버퍼 전체를 보관 용량에 포함', () => {
  const mesh = {
    positions: new Float32Array(1024).subarray(0, 9),
    normals: new Float32Array(1024).subarray(0, 9),
    bounds: new Float32Array(6),
    ends: [1],
  };
  const cache = new BuildingMeshCache(212);
  cache.put('a', mesh);
  expect(cache.get('a')).toBeUndefined();
});
