import { expect, test } from 'vitest';
import { ExtrudeGeometry } from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import { buildBuildingMesh } from './buildingGeometryService';
import { buildingFaceIndex } from './buildingSelectionService';
import type { CityBuilding } from '../entity/city';

test('별도 스레드 전송 형상의 구멍·높이·면 순서와 원본 선택 보존', () => {
  const outer: [number, number][] = [
    [0, 0],
    [30, 0],
    [30, 30],
    [0, 30],
    [0, 0],
  ];
  const hole: [number, number][] = [
    [10, 10],
    [10, 20],
    [20, 20],
    [20, 10],
    [10, 10],
  ];
  const buildings: CityBuilding[] = [
    {
      id: 'way/1',
      polygons: [[outer, hole]],
      heightM: 12,
      center: [15, 15],
      areaM2: 800,
      heightSource: 'OSM_HEIGHT_TAG',
    },
    {
      id: 'way/2',
      polygons: [[outer.map(([x, y]) => [x + 50, y])]],
      heightM: 35,
      center: [65, 15],
      areaM2: 900,
      heightSource: 'OSM_HEIGHT_TAG',
    },
  ];
  const before = structuredClone(buildings);
  const parts = buildings.map(
    (b) =>
      new ExtrudeGeometry(polygonShapes(b.polygons), {
        depth: b.heightM,
        bevelEnabled: false,
        steps: 1,
      })
  );
  const original = mergeGeometries(parts)!;
  const data = buildBuildingMesh(buildings);
  expect(data.positions).toEqual(original.getAttribute('position').array);
  expect(data.normals).toEqual(original.getAttribute('normal').array);
  expect(buildingFaceIndex(data.ends, data.ends[0] - 1)).toBe(0);
  expect(buildingFaceIndex(data.ends, data.ends[0])).toBe(1);
  expect(buildings).toEqual(before);
  const elevated = buildBuildingMesh(buildings.map((b) => ({ ...b, baseElevationM: 123 })));
  expect(elevated.ends).toEqual(data.ends);
  expect(elevated.normals).toEqual(data.normals);
  for (let i = 0; i < data.positions.length; i++)
    expect(elevated.positions[i]).toBe(data.positions[i] + (i % 3 === 2 ? 123 : 0));
  original.dispose();
  parts.forEach((p) => p.dispose());
});
