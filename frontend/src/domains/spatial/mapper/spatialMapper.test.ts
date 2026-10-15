import { describe, expect, it } from 'vitest';
import { mapSpatial } from './spatialMapper';

// 외부 원본을 저장하지 않는 응답 계약 시험 도형.
const sample = {
  provider: '시험',
  layer: 'LT_C_SPBD',
  requestedCrs: 'EPSG:4326',
  sourceUrl: 'https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=spbd&apiVer=2',
  retrievedAt: '2026-10-15T00:00:00Z',
  use: 'DISPLAY_COMPARISON_ONLY',
  rawRetained: false,
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
    expect(value.rawRetained).toBe(false);
  });
  it('중복·잘못된 좌표계·연구 입력 승격 거부', () => {
    expect(() =>
      mapSpatial({ ...sample, buildings: [...sample.buildings, ...sample.buildings] })
    ).toThrow();
    expect(() => mapSpatial({ ...sample, requestedCrs: 'EPSG:3857' })).toThrow();
    expect(() => mapSpatial({ ...sample, use: 'CALIBRATED' })).toThrow();
  });
});
