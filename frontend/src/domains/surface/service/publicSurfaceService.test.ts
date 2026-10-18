import { expect, test } from 'vitest';
import { publicSurfaceDto, type PublicSurfaceCurrent } from '../dto/publicSurfaceDto';
import type { SurfaceFrame } from '../entity/surface';
import { bindPublicFrame, currentPublicFrames } from './publicSurfaceService';
const run: PublicSurfaceCurrent['runs'][number] = {
  id: '00000000-0000-4000-8000-000000000001',
  basinId: 'test-only',
  name: '전달 시험 전용',
  inputBundleSha256: 'a'.repeat(64),
  numericalPolicySha256: 'b'.repeat(64),
  lastFrameAt: '2026-10-19T00:00:00Z',
  catalog: {
    schemaVersion: 2,
    catalogSha256: 'c'.repeat(64),
    surfaceResultSha256: 'd'.repeat(64),
    classification: 'PUBLIC_INPUT_UNCALIBRATED_CURRENT_BASELINE',
    startUtc: '2026-10-19T00:00:00Z',
    coordinateSystem: 'EPSG:5186',
    originProjected: [198128, 551989],
    verticalPlacement: 'TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION',
    triangleCount: 1,
    timesSeconds: [0],
    limitations: ['합성 전달 검사 전용 · 운영 자료 아님'],
    flowDirectionMethod: 'SOURCE_MOMENTUM_LOCAL_PROJECTION_JACOBIAN_V1',
  },
};
const current = { serverNow: '2026-10-19T00:00:01Z', runs: [run] };
const now = Date.parse(current.serverNow);
const frame: SurfaceFrame = {
  catalogSha256: run.catalog.catalogSha256,
  sourceSha256: 'e'.repeat(64),
  index: 0,
  timeSeconds: 0,
  wholeDomainStorageM3: 0.2,
  cells: [
    {
      triangleId: 0,
      vertices: [
        [0, 0],
        [1, 0],
        [0, 1],
      ],
      depthM: 0.4,
      speedMps: 0.5,
      flowDirection: [1, 0],
    },
  ],
};
test('공개 목록은 중복 유역·회원 시나리오·시각 불일치 거부', () => {
  expect(publicSurfaceDto.safeParse(current).success).toBe(true);
  for (const runs of [
    [run, run],
    [run, { ...run, id: '00000000-0000-4000-8000-000000000002' }],
    [{ ...run, catalog: { ...run.catalog, classification: 'PRIVATE_DESIGN' } }],
    [{ ...run, lastFrameAt: '2026-10-19T00:00:01Z' }],
  ])
    expect(publicSurfaceDto.safeParse({ ...current, runs }).success).toBe(false);
});
test('오래되거나 미래인 프레임은 표시하지 않고 유효 프레임의 원값 보존', () => {
  const before = JSON.stringify(frame),
    bound = bindPublicFrame(run, frame, now);
  expect(bound.frame).toBe(frame);
  expect(currentPublicFrames(current, [bound], now)).toEqual([bound]);
  expect(currentPublicFrames(current, [bound], now + 299000)).toEqual([bound]);
  expect(currentPublicFrames(current, [bound], now + 299001)).toEqual([]);
  expect(currentPublicFrames(current, [bound], now - 1001)).toEqual([]);
  expect(() => bindPublicFrame(run, frame, now + 299001)).toThrow();
  expect(JSON.stringify(frame)).toBe(before);
});
test('게시 취소·해시 변경·다른 유역을 즉시 제외', () => {
  const bound = bindPublicFrame(run, frame, now);
  expect(currentPublicFrames(null, [bound], now)).toEqual([]);
  expect(currentPublicFrames({ ...current, runs: [] }, [bound], now)).toEqual([]);
  expect(currentPublicFrames(current, [{ ...bound, basinId: 'other' }], now)).toEqual([]);
  expect(
    currentPublicFrames(
      current,
      [{ ...bound, frame: { ...frame, catalogSha256: 'f'.repeat(64) } }],
      now
    )
  ).toEqual([]);
  expect(() => bindPublicFrame(run, { ...frame, catalogSha256: 'f'.repeat(64) }, now)).toThrow();
});
test('독립 유역은 별도 원 프레임으로 유지하고 물량 합산 없음', () => {
  const second = {
    ...run,
    id: '00000000-0000-4000-8000-000000000002',
    basinId: 'second-test-only',
  };
  const frames = [bindPublicFrame(run, frame, now), bindPublicFrame(second, frame, now)];
  const actual = currentPublicFrames({ ...current, runs: [run, second] }, frames, now);
  expect(actual).toHaveLength(2);
  expect(actual.map((value) => value.frame.wholeDomainStorageM3)).toEqual([0.2, 0.2]);
  expect(actual[0].frame).toBe(frame);
});
