import { afterEach, expect, test, vi } from 'vitest';
import { BufferAttribute, BufferGeometry } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import { partBounds } from '../../../shared/repository/meshBounds';
import { streetGeometry } from './streetGeometryService';
import { StreetMeshBuilder } from './streetMeshService';

const road = (id: string, x = 0): Street => ({
  id,
  class: 'residential',
  districtId: '11110',
  widthM: 8,
  widthSource: 'DISPLAY_ASSUMPTION',
  walk: false,
  motor: true,
  oneway: 0,
  sidewalk: 'both',
  bridge: true,
  coordinates: [
    [x, 0],
    [x + 30, 0],
  ],
});
const signal = () => new AbortController().signal;
afterEach(() => vi.restoreAllMocks());

function reference(
  roads: Street[],
  terrain: Terrain | null,
  detail: boolean,
  center?: [number, number]
) {
  const data = streetGeometry(roads, terrain, detail, [], center);
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return {
    ...data,
    normals: geometry.getAttribute('normal').array,
    bounds: partBounds(data.positions, data.ends),
    sphere: [...geometry.boundingSphere!.center.toArray(), geometry.boundingSphere!.radius],
  };
}

test('개별 재사용의 상판·난간·색·법선·클릭 순서가 기존 전체 생성과 일치', async () => {
  const roads = [
    road('near'),
    road('far', 2000),
    { ...road('path'), nativeSourceRole: 'ROAD_CENTERLINE' },
  ];
  const builder = new StreetMeshBuilder();
  for (const center of [
    [0, 0],
    [1000, 0],
    [2500, 0],
    [0, 0],
  ] as [number, number][]) {
    const result = await builder.build(structuredClone(roads), null, true, [], center, signal());
    expect(result).toEqual(reference(roads, null, true, center));
  }
  expect(builder.statistics.generated).toBe(6);
  expect(builder.statistics.reused).toBe(6);
});

test('인접 타일 이동은 유지 도로를 재사용하고 같은 식별자의 높이·차선 변경은 반영', async () => {
  const builder = new StreetMeshBuilder();
  const a = road('a'),
    b = road('b'),
    c = road('c');
  await builder.build([a, b], null, true, [], [0, 0], signal());
  await builder.build(structuredClone([b, c]), null, true, [], [500, 0], signal());
  expect(builder.statistics).toMatchObject({ generated: 3, reused: 1 });
  const changed = { ...b, widthM: 12, lanes: 3, elevationsM: [20, 25] };
  expect(await builder.build([changed], null, true, [], [500, 0], signal())).toEqual(
    reference([changed], null, true, [500, 0])
  );
  expect(builder.statistics.generated).toBe(4);
});

test('지형 교체·주차 통로 분류를 캐시 키에 반영하고 원거리 이동은 재생성하지 않음', async () => {
  const builder = new StreetMeshBuilder();
  const roads = [road('a')];
  const terrain: Terrain = {
    width: 2,
    height: 2,
    origin: [0, 0],
    spacing: [50, 50],
    districtIds: [],
    heights: new Float32Array(4).fill(10),
    districts: new Uint8Array(4),
    cover: new Uint8Array(4),
  };
  await builder.build(roads, null, false, [], [0, 0], signal());
  await builder.build(roads, null, false, [], [9000, 0], signal());
  expect(builder.statistics).toMatchObject({ generated: 1, reused: 1 });
  const elevated = await builder.build(roads, terrain, false, [], [9000, 0], signal());
  expect(elevated).toEqual(reference(roads, terrain, false, [9000, 0]));
  await builder.build(roads, terrain, false, ['a'], [9000, 0], signal());
  expect(builder.statistics.generated).toBe(3);
});

test('합본 버퍼를 이전해도 재사용 버퍼와 도로 클릭 인덱스는 보존', async () => {
  const builder = new StreetMeshBuilder();
  const roads = [road('a'), road('b', 100)];
  const first = await builder.build(roads, null, true, [], [0, 0], signal());
  const transferred = structuredClone(first, {
    transfer: [
      first.positions.buffer,
      first.colors.buffer,
      first.normals.buffer,
      first.bounds.buffer,
    ],
  });
  expect(first.positions.byteLength).toBe(0);
  const next = await builder.build(roads, null, true, [], [500, 0], signal());
  expect(next).toEqual(transferred);
  expect(builder.statistics).toMatchObject({ generated: 2, reused: 2 });
});

test('캐시 한도 초과 형상은 보관하지 않고 빈 목록도 유효한 메시로 반환', async () => {
  const builder = new StreetMeshBuilder(1);
  for (let i = 0; i < 2; i++) await builder.build([road('a')], null, true, [], undefined, signal());
  expect(builder.statistics).toEqual({ generated: 2, reused: 0, bytes: 0 });
  expect(await builder.build([], null, true, [], undefined, signal())).toEqual(
    reference([], null, true)
  );
});

test('현재 시야가 캐시 한도보다 커도 보관된 도로를 서로 밀어내지 않음', async () => {
  const sample = new StreetMeshBuilder();
  await sample.build([road('a')], null, true, [], undefined, signal());
  const maximum = Math.floor(sample.statistics.bytes * 1.5);
  const builder = new StreetMeshBuilder(maximum);
  const roads = [road('a'), road('b')];
  await builder.build(roads, null, true, [], undefined, signal());
  expect(builder.statistics.generated).toBe(2);
  expect(await builder.build(roads, null, true, [], undefined, signal())).toEqual(
    reference(roads, null, true)
  );
  expect(builder.statistics).toMatchObject({ generated: 3, reused: 1 });
  expect(builder.statistics.bytes).toBeLessThanOrEqual(maximum);
  const moved = [road('b'), road('c')];
  await builder.build(moved, null, true, [], undefined, signal());
  await builder.build(moved, null, true, [], undefined, signal());
  expect(builder.statistics).toMatchObject({ generated: 6, reused: 2 });
  expect(builder.statistics.bytes).toBeLessThanOrEqual(maximum);
});

test('이동 중 취소는 남은 도로 계산을 멈추고 완성된 부분만 다음 요청에서 재사용', async () => {
  let now = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => (now += 10));
  const builder = new StreetMeshBuilder(),
    controller = new AbortController();
  const roads = [road('a'), road('b')];
  const request = builder.build(roads, null, true, [], undefined, controller.signal);
  const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
  controller.abort();
  await rejected;
  expect(builder.statistics.generated).toBe(1);
  expect(await builder.build(roads, null, true, [], undefined, signal())).toEqual(
    reference(roads, null, true)
  );
  expect(builder.statistics).toMatchObject({ generated: 2, reused: 1 });
  await expect(
    builder.build(roads, null, true, [], undefined, controller.signal)
  ).rejects.toMatchObject({ name: 'AbortError' });
  expect(builder.statistics.generated).toBe(2);
});
