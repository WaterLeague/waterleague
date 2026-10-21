import { expect, test } from 'vitest';
import { BufferAttribute, BufferGeometry } from 'three';
import { createTerrainGeometry, terrainMeshData } from './terrainMeshService';
import type { Terrain } from '../entity/terrain';

test('같은 지형의 좌표·법선 재사용과 장면별 색상·GPU 속성 격리', () => {
  const terrain: Terrain = {
    width: 3,
    height: 2,
    origin: [0, 90],
    spacing: [90, -90],
    districtIds: ['1'],
    heights: new Float32Array([10, 20, 30, 40, 50, 60]),
    districts: new Uint8Array([1, 0, 0, 0, 0, 0]),
    cover: new Uint8Array(6),
  };
  const first = createTerrainGeometry(terrain),
    second = createTerrainGeometry(terrain);
  expect(terrainMeshData(terrain)).toBe(terrainMeshData(terrain));
  expect(first.getAttribute('position').array).toBe(second.getAttribute('position').array);
  expect(first.getAttribute('position')).not.toBe(second.getAttribute('position'));
  expect(first.getAttribute('normal').array).toBe(second.getAttribute('normal').array);
  expect(first.getAttribute('color').array).not.toBe(second.getAttribute('color').array);
  expect([...first.index!.array]).toEqual([0, 3, 1, 1, 3, 4]);
  expect([...first.getAttribute('position').array]).toEqual([
    0, 10, -90, 90, 20, -90, 180, 30, -90, 0, 40, -0, 90, 50, -0, 180, 60, -0,
  ]);
  const original = new BufferGeometry();
  original.setAttribute(
    'position',
    new BufferAttribute(first.getAttribute('position').array.slice(), 3)
  );
  original.setIndex([0, 3, 1, 1, 3, 4]);
  original.computeVertexNormals();
  expect(first.getAttribute('normal').array).toEqual(original.getAttribute('normal').array);
  first.getAttribute('color').setXYZW(0, 1, 0, 0, 0.2);
  expect(second.getAttribute('color').getX(0)).toBe(0);
  first.dispose();
  expect(second.getAttribute('position').getY(0)).toBe(10);
  expect(
    terrainMeshData({ ...terrain, heights: new Float32Array([11, 20, 30, 40, 50, 60]) })
      .positions[1]
  ).toBe(11);
  second.dispose();
  original.dispose();
});

test('대회에서 제외한 구의 지형 삼각형을 GPU 색인에서 제외', () => {
  const terrain: Terrain = {
    width: 3,
    height: 2,
    origin: [0, 1],
    spacing: [1, -1],
    districtIds: ['11110', '11680'],
    heights: new Float32Array(6),
    districts: new Uint8Array([1, 1, 2, 1, 1, 2]),
    cover: new Uint8Array(6),
  };
  const before = createTerrainGeometry(terrain);
  const selected = createTerrainGeometry(terrain, ['11110']);
  expect([...selected.index!.array]).toEqual([0, 3, 1, 1, 3, 4]);
  expect(before.index!.array.length).toBe(12);
  expect(selected.getAttribute('position').array).toBe(before.getAttribute('position').array);
  before.dispose();
  selected.dispose();
});
