import { expect, test } from 'vitest';
import indexSource from '../../../../public/data/seoul-features-v1/index.json';
import sampleSource from '../__tests__/fixtures/native-layer-samples-v1.json';
import { topographyIndexDto, topographyTileDto } from '../dto/topographyDto';
import { topographyGeometry } from './topographyGeometryService';
import { nearbyTopographyTiles } from './topographyVisibilityService';
import { bridgeTransportBindings } from '../../urban/service/nativeBridgeTransportService';
import type { NativeBridgeGroup } from '../../urban/dto/nativeBridgeDto';
const index = topographyIndexDto.parse(indexSource),
  samples = topographyTileDto.parse(sampleSource);

test('하부 차도 위에 겹친 상부 보도·난간은 한 번만 올리고 횡단하는 하부 난간은 지면 유지', () => {
  const rect = (x: number, y: number, w: number, h: number): [number, number][][][] => [
    [
      [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
        [x, y],
      ],
    ],
  ];
  const group = {
    polygons: rect(0, -5, 100, 10),
    profiles: [
      {
        coordinates: [
          [0, 0],
          [100, 0],
        ],
        span: [0, 100],
        roadIds: ['road'],
        polygons: [],
        displayWidthM: 10,
      },
    ],
    sidewalks: [{ polygons: rect(0, 3, 100, 2) }],
    preservedUnderpassPolygons: rect(47, -5, 6, 10),
    surfaceCuts: [{ roles: ['SIDEWALK_AREA'], polygons: rect(0, 3, 100, 2) }],
  } as unknown as NativeBridgeGroup;
  const bindings = bridgeTransportBindings([group]);
  const layer = index.layers.findIndex((l) => l.id.startsWith('N1L_C053'));
  for (const [part, upper] of [
    [
      [
        [20, 4],
        [80, 4],
      ],
      true,
    ],
    [
      [
        [48, -20],
        [48, 20],
      ],
      false,
    ],
  ] as const) {
    const mesh = topographyGeometry(
      {
        schemaVersion: 1,
        id: '0_0',
        areas: [],
        points: [],
        lines: [[layer, 1, [part.map((p) => [...p] as [number, number])], null]],
      },
      index.layers,
      null,
      false,
      true,
      bindings
    );
    const heights = Array.from(mesh.positions).filter((_, i) => i % 3 === 1);
    expect(heights.length).toBeGreaterThan(0);
    if (upper) expect(Math.min(...heights)).toBeGreaterThan(6.5);
    else expect(Math.max(...heights)).toBeLessThan(1.2);
  }
  const sidewalk = index.layers.findIndex((l) => l.role === 'SIDEWALK_AREA');
  const ground = topographyGeometry(
    {
      schemaVersion: 1,
      id: '0_0',
      points: [],
      lines: [],
      areas: [[sidewalk, 2, rect(47, 3, 6, 2), null]],
    },
    index.layers,
    null,
    false,
    true,
    bindings
  );
  expect(ground.positions.length).toBe(0);
});
test('교량 전용 레이어 사용 시 원 교량·육교·입체교차부 지면 사본을 생성하지 않고 2D 유지', () => {
  for (const role of [
    'BRIDGE_AREA',
    'PEDESTRIAN_OVERPASS_AREA',
    'GRADE_SEPARATED_INTERSECTION_AREA',
  ]) {
    const tile = {
      ...samples,
      points: [],
      lines: [],
      areas: samples.areas.filter(([layer]) => index.layers[layer].role === role),
    };
    expect(tile.areas.length).toBeGreaterThan(0);
    const mesh = topographyGeometry(tile, index.layers, null, false, true);
    expect(mesh.positions.length + mesh.lines.length).toBe(0);
    expect(topographyGeometry(tile, index.layers, null, true, true).plan.some((p) => p.areas)).toBe(
      true
    );
  }
});
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
test('도로면·교차로는 동일 높이로 접합하고 보도와 배경 도로의 깊이 구분', () => {
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
  expect(elevations[1]).toBe(elevations[2]);
  expect(new Set(elevations).size).toBe(3);
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

test('터널·지하도 입구는 빈 통행 공간을 가진 문틀, 잔교는 폭과 상판을 가진 구조', () => {
  for (const [name, top] of [
    ['N1L_A0123373', 5.3],
    ['N1L_C0463374', 3.1],
    ['N1L_C0080000', 1.05],
  ] as const) {
    const layer = index.layers.findIndex((l) => l.id === name);
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
                [10, 0],
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
    expect(mesh.lines.length).toBe(0);
    const heights = Array.from(mesh.positions).filter((_, i) => i % 3 === 1);
    expect(Math.max(...heights)).toBeCloseTo(top);
    const middleHeights: number[] = [];
    for (let i = 0; i < mesh.positions.length; i += 3)
      if (mesh.positions[i] > 1 && mesh.positions[i] < 9) middleHeights.push(mesh.positions[i + 1]);
    if (name !== 'N1L_C0080000') expect(middleHeights.every((h) => h >= top - 0.51)).toBe(true);
    else
      expect(Math.max(...Array.from(mesh.positions).filter((_, i) => i % 3 === 2))).toBeCloseTo(
        1.2
      );
  }
});

test('승강장 지붕은 지면까지 채운 블록 없이 기둥과 얇은 지붕으로 생성', () => {
  const layer = index.layers.findIndex((l) => l.id === 'N1A_A0201222');
  const mesh = topographyGeometry(
    {
      schemaVersion: 1,
      id: '0_0',
      points: [],
      lines: [],
      areas: [
        [
          layer,
          1,
          [
            [
              [
                [0, 0],
                [30, 0],
                [30, 10],
                [0, 10],
                [0, 0],
              ],
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
  const heights = Array.from(mesh.positions).filter((_, i) => i % 3 === 1);
  expect(Math.max(...heights)).toBeCloseTo(4.2);
  expect(heights.some((h) => Math.abs(h - 3.95) < 1e-5)).toBe(true);
  expect(heights.some((h) => Math.abs(h - 0.65) < 1e-5)).toBe(true);
  expect(heights.every((h) => h >= 0.64)).toBe(true);
});
