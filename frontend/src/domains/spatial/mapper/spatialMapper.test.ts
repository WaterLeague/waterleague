import { describe, expect, it } from 'vitest';
import { mapSpatial } from './spatialMapper';

// 운영 관측과 분리한 응답 계약 시험 도형.
const sample = {
  provider: '국토지리정보원',
  layer: 'N1A_B0010000',
  requestedCrs: 'EPSG:4326',
  sourceUrl: 'https://www.data.go.kr/data/15059719/fileData.do',
  retrievedAt: '2026-10-17T00:00:00Z',
  dataYear: 2025,
  snapshotHash: 'a'.repeat(64),
  use: 'DISPLAY_COMPARISON_ONLY',
  rawRetained: true,
  bounds: [127.0525, 37.543, 127.0555, 37.5455],
  buildings: [
    {
      id: 'test-1',
      name: '시험',
      aboveGroundFloors: null,
      polygons: [
        [
          [
            [127.054, 37.544],
            [127.0541, 37.544],
            [127.0541, 37.5441],
            [127.054, 37.544],
          ],
        ],
      ],
    },
  ],
};
describe('공간자료 화면 계약', () => {
  it('미확인 층수와 화면 대조 용도 보존', () => {
    const value = mapSpatial(sample);
    expect(value.buildings[0].aboveGroundFloors).toBeNull();
    expect(value.rawRetained).toBe(true);
    expect(value.retrievedAt).toBe(sample.retrievedAt);
    expect(value.snapshotHash).toBe(sample.snapshotHash);
  });
  it('중복·잘못된 좌표계·연구 입력 승격 거부', () => {
    expect(() =>
      mapSpatial({ ...sample, buildings: [...sample.buildings, ...sample.buildings] })
    ).toThrow();
    expect(() => mapSpatial({ ...sample, requestedCrs: 'EPSG:3857' })).toThrow();
    expect(() => mapSpatial({ ...sample, use: 'CALIBRATED' })).toThrow();
    expect(() => mapSpatial({ ...sample, snapshotHash: 'missing' })).toThrow();
    expect(() => mapSpatial({ ...sample, dataYear: 2024 })).toThrow();
    expect(() => mapSpatial({ ...sample, rawRetained: false })).toThrow();
  });
});
