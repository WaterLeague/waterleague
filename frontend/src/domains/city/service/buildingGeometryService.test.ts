import { expect, test } from 'vitest';
import {
  BufferGeometry,
  Float32BufferAttribute,
  ExtrudeGeometry,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
  DoubleSide,
} from 'three';
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
      id: 'ngii:N1A_B0010000:' + '1'.repeat(64),
      polygons: [[outer, hole]],
      heightM: 12,
      center: [15, 15],
      areaM2: 800,
      heightSource: 'FLOOR_COUNT_DISPLAY_ASSUMPTION',
      districtId: '11200',
      candidateId: null,
      geometryEligibility: 'GEOMETRY_ONLY',
    },
    {
      id: 'ngii:N1A_B0010000:' + '2'.repeat(64),
      polygons: [[outer.map(([x, y]) => [x + 50, y])]],
      heightM: 35,
      center: [65, 15],
      areaM2: 900,
      heightSource: 'FLOOR_COUNT_DISPLAY_ASSUMPTION',
      districtId: '11200',
      candidateId: null,
      geometryEligibility: 'GEOMETRY_ONLY',
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
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(data.positions, 3));
  geometry.setAttribute('normal', new Float32BufferAttribute(data.normals, 3));
  const measures = (value: BufferGeometry) => {
    const p = value.getAttribute('position'),
      a = new Vector3(),
      b = new Vector3(),
      c = new Vector3();
    let area = 0,
      volume = 0;
    for (let i = 0; i < p.count; i += 3) {
      a.fromBufferAttribute(p, i);
      b.fromBufferAttribute(p, i + 1);
      c.fromBufferAttribute(p, i + 2);
      volume += a.dot(b.clone().cross(c)) / 6;
      area += b.sub(a).cross(c.sub(a)).length() / 2;
    }
    value.computeBoundingBox();
    return {
      area,
      volume,
      bounds: [...value.boundingBox!.min.toArray(), ...value.boundingBox!.max.toArray()],
    };
  };
  expect(measures(geometry)).toEqual(measures(original));
  const material = new MeshBasicMaterial({ side: DoubleSide }),
    beforeMesh = new Mesh(original, material),
    afterMesh = new Mesh(geometry, material);
  for (const x of [5, 15, 25, 55, 65, 75])
    for (const y of [5, 15, 25]) {
      const ray = new Raycaster(new Vector3(x, y, 100), new Vector3(0, 0, -1));
      const distances = (mesh: Mesh) =>
        [...new Set(ray.intersectObject(mesh).map((hit) => hit.distance))].sort();
      expect(distances(afterMesh)).toEqual(distances(beforeMesh));
    }
  material.dispose();
  geometry.dispose();
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
