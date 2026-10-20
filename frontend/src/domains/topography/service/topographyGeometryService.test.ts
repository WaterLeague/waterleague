import { expect, test } from 'vitest';
import indexSource from '../../../../public/data/seoul-features-v1/index.json';
import sampleSource from '../__tests__/fixtures/native-layer-samples-v1.json';
import { topographyIndexDto, topographyTileDto } from '../dto/topographyDto';
import { topographyGeometry } from './topographyGeometryService';
import { nearbyTopographyTiles } from './topographyVisibilityService';
const index = topographyIndexDto.parse(indexSource),
  samples = topographyTileDto.parse(sampleSource);
test('121종 실제 원본 대표 도형의 2D·3D 표시와 원형 불변 검증', () => {
  const before = structuredClone(samples);
  for (let layer = 0; layer < 121; layer++) {
    const tile = {
      schemaVersion: 1 as const,
      id: '0_0',
      points: samples.points.filter((row) => row[0] === layer),
      lines: samples.lines.filter((row) => row[0] === layer),
      areas: samples.areas.filter((row) => row[0] === layer),
    };
    expect(tile.points.length + tile.lines.length + tile.areas.length).toBe(1);
    const mesh = topographyGeometry(tile, index.layers, null, false),
      plan = topographyGeometry(tile, index.layers, null, true);
    expect(
      mesh.positions.length +
        mesh.lines.length +
        mesh.models.reduce((sum, m) => sum + m.matrices.length, 0) +
        mesh.labels.length,
      index.layers[layer].id
    ).toBeGreaterThan(0);
    expect(
      plan.plan.some((part) => part.areas || part.lines || part.points),
      index.layers[layer].id
    ).toBe(true);
    expect(plan.positions.length + plan.lines.length).toBe(0);
    for (const value of Object.values(mesh))
      if (value instanceof Float32Array) expect(value.every(Number.isFinite)).toBe(true);
  }
  expect(samples).toEqual(before);
});
test('행정·도곽·하천 경계는 도로·수면을 덮지 않는 경계 표시', () => {
  for (const name of ['N1A_G0010000', 'N1A_H0010000', 'N1A_E0010001']) {
    const layer = index.layers.findIndex((value) => value.id === name);
    const tile = {
      schemaVersion: 1 as const,
      id: '0_0',
      points: [],
      lines: [],
      areas: samples.areas.filter((row) => row[0] === layer),
    };
    const mesh = topographyGeometry(tile, index.layers, null, false);
    expect(mesh.positions.length).toBe(0);
    expect(mesh.lines.length).toBeGreaterThan(0);
  }
});
test('시야 타일은 가까운 순서이며 임의 건수 상한으로 일부 지물을 누락하지 않음', () => {
  const center: [number, number] = [0, 0],
    distance = 2500,
    radius = distance * 0.72;
  const wanted = nearbyTopographyTiles(index, center, distance);
  expect(wanted.length).toBeGreaterThan(9);
  const expected = index.tiles.filter(
    (tile) =>
      tile.bounds[0] <= radius &&
      tile.bounds[2] >= -radius &&
      tile.bounds[1] <= radius &&
      tile.bounds[3] >= -radius
  );
  expect(new Set(wanted.map((tile) => tile.id))).toEqual(new Set(expected.map((tile) => tile.id)));
  expect(nearbyTopographyTiles(index, [NaN, 0], 100)).toEqual([]);
});
test('도로면·교차로·보도는 서로 다른 깊이의 면으로 생성', () => {
  const elevations: number[] = [];
  for (const name of ['N3A_A0010000', 'N1A_A0010000', 'N1A_A0080000', 'N1A_A0033320']) {
    const layer = index.layers.findIndex((row) => row.id === name);
    const tile = {
      schemaVersion: 1 as const,
      id: '0_0',
      points: [],
      lines: [],
      areas: samples.areas.filter((row) => row[0] === layer),
    };
    const mesh = topographyGeometry(tile, index.layers, null, false);
    expect(mesh.positions.length).toBeGreaterThan(0);
    const tops = Array.from(mesh.positions).filter((_, i) => i % 3 === 1);
    elevations.push(Math.max(...tops));
  }
  expect(elevations).toEqual([...elevations].sort((a, b) => a - b));
  expect(new Set(elevations).size).toBe(4);
});
test('원 도로중심선과 보행 선형은 입체 면으로 표시', () => {
  for (const id of ['N1L_A0020000', 'N1L_A0033330']) {
    const layer = index.layers.findIndex((l) => l.id === id);
    const mesh = topographyGeometry(
      {
        schemaVersion: 1,
        id: '0_0',
        points: [],
        areas: [],
        lines: [
          [
            layer,
            1,
            [
              [
                [0, 0],
                [50, 0],
                [50, 50],
              ],
            ],
            null,
          ],
        ],
      },
      index.layers,
      null,
      false
    );
    expect(mesh.positions.length).toBeGreaterThan(0);
    expect(mesh.lines.length).toBe(0);
    expect(mesh.positions.every(Number.isFinite)).toBe(true);
  }
});
