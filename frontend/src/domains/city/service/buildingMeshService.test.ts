import { afterEach, expect, test, vi } from 'vitest';
import type { CityBuilding } from '../entity/city';
import { buildBuildingMesh } from './buildingGeometryService';
import { BuildingMeshBuilder } from './buildingMeshService';
import { buildingFaceIndex } from './buildingSelectionService';

const building = (id: string, x = 0): CityBuilding => ({
  id: `ngii:N1A_B0010000:${id.padStart(64, '0')}`,
  heightM: 12,
  baseElevationM: 9.25,
  center: [x + 15, 15],
  areaM2: 900,
  heightSource: 'FLOOR_COUNT_DISPLAY_ASSUMPTION',
  districtId: '11200',
  candidateId: null,
  geometryEligibility: 'GEOMETRY_ONLY',
  polygons: [
    [
      [
        [x, 0],
        [x + 30, 0],
        [x + 30, 30],
        [x, 30],
        [x, 0],
      ],
    ],
  ],
});
const signal = () => new AbortController().signal;
afterEach(() => vi.restoreAllMocks());

test('순서·설치 표시 묶음 변경에서도 구멍·다중 도형·법선·건물 클릭 범위 보존', async () => {
  const a = building('a');
  a.polygons[0].push([
    [10, 10],
    [10, 20],
    [20, 20],
    [20, 10],
    [10, 10],
  ]);
  a.polygons.push(...building('part', 50).polygons);
  const b = building('b', 100),
    c = building('c', 200),
    builder = new BuildingMeshBuilder();
  const before = structuredClone([a, b, c]);
  for (const group of [[a, b, c], [c, a], [b], [a, b, c]]) {
    const result = await builder.build(structuredClone(group), signal());
    expect(result).toEqual(buildBuildingMesh(group));
    for (let i = 0; i < group.length; i++) {
      expect(buildingFaceIndex(result.ends, i ? result.ends[i - 1] : 0)).toBe(i);
      expect(buildingFaceIndex(result.ends, result.ends[i] - 1)).toBe(i);
    }
  }
  expect(builder.statistics).toMatchObject({ generated: 3, reused: 6 });
  expect([a, b, c]).toEqual(before);
});

test('같은 식별자의 실제 형상·높이·표고 변경만 새로 생성', async () => {
  const builder = new BuildingMeshBuilder(),
    a = building('a'),
    b = building('b', 100);
  await builder.build([a, b], signal());
  for (const changed of [
    { ...a, heightM: 20 },
    { ...a, baseElevationM: 40 },
    { ...a, polygons: building('a', 300).polygons },
  ]) {
    expect(await builder.build([changed, structuredClone(b)], signal())).toEqual(
      buildBuildingMesh([changed, b])
    );
  }
  expect(builder.statistics).toMatchObject({ generated: 5, reused: 3 });
});

test('전송 버퍼 분리 후 재사용·빈 목록과 기존 선택 범위 유지', async () => {
  const builder = new BuildingMeshBuilder(),
    source = [building('a'), building('b', 100)];
  const first = await builder.build(source, signal());
  const received = structuredClone(first, {
    transfer: [first.positions.buffer, first.normals.buffer, first.bounds.buffer],
  });
  expect(first.positions.byteLength).toBe(0);
  expect(await builder.build(structuredClone(source), signal())).toEqual(received);
  expect(builder.statistics).toMatchObject({ generated: 2, reused: 2 });
  expect(await builder.build([], signal())).toEqual(buildBuildingMesh([]));
});

test('시야가 한도를 넘어도 현재 건물 캐시를 서로 밀어내지 않고 이전 시야만 정리', async () => {
  const sample = new BuildingMeshBuilder(),
    a = building('a'),
    b = building('b'),
    c = building('c');
  await sample.build([a], signal());
  const maximum = Math.floor(sample.statistics.bytes * 1.5),
    builder = new BuildingMeshBuilder(maximum);
  for (const group of [
    [a, b],
    [a, b],
    [b, c],
    [b, c],
  ]) {
    expect(await builder.build(group, signal())).toEqual(buildBuildingMesh(group));
    expect(builder.statistics.bytes).toBeLessThanOrEqual(maximum);
  }
  expect(builder.statistics).toMatchObject({ generated: 6, reused: 2 });
  const disabled = new BuildingMeshBuilder(0);
  for (let i = 0; i < 2; i++)
    expect(await disabled.build([a], signal())).toEqual(buildBuildingMesh([a]));
  expect(disabled.statistics).toEqual({ generated: 2, reused: 0, bytes: 0 });
});

test('이동 중 취소는 완성한 건물만 보존하고 다음 요청에서 나머지 형상 생성', async () => {
  let calls = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => Math.max(0, ++calls - 3) * 10);
  const builder = new BuildingMeshBuilder(),
    controller = new AbortController(),
    source = [building('a'), building('b', 100)];
  const request = builder.build(source, controller.signal);
  const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
  controller.abort();
  await rejected;
  expect(builder.statistics.generated).toBe(1);
  expect(await builder.build(source, signal())).toEqual(buildBuildingMesh(source));
  expect(builder.statistics).toMatchObject({ generated: 2, reused: 1 });
  await expect(builder.build(source, controller.signal)).rejects.toMatchObject({
    name: 'AbortError',
  });
  expect(builder.statistics.generated).toBe(2);
});
