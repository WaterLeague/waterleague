import { expect, test, vi } from 'vitest';
import cityJson from '../../../../public/data/seoul-native-v1/city.json';
import type { City } from '../entity/city';
import { currentLocation, seoulLocation } from './currentLocationService';

const city = cityJson as unknown as City;
// 지도 생성에 사용하는 pyproj 3.8.0의 EPSG:4326 → 5186 독립 변환 결과.
test.each([
  ['서울시청', 126.978, 37.5665, -71.63326297296, -103.96941128362, '중구'],
  ['강남역', 127.0276, 37.4979, 4312.61062931956, -7717.59141624474, '서초구'],
  ['김포공항', 126.8017, 37.5585, -15649.08582344907, -973.62030898954, '강서구'],
])(
  '%s 위치를 원 서울 경계로 판정하고 지도 좌표로 변환',
  async (_, longitude, latitude, x, y, district) => {
    const result = await seoulLocation(city, { longitude, latitude });
    expect(result.center[0]).toBeCloseTo(x, 2);
    expect(result.center[1]).toBeCloseTo(y, 2);
    expect(result.districtName).toBe(district);
  }
);

test.each([
  ['광명', 126.8647, 37.4785],
  ['과천', 126.9878, 37.4292],
  ['부산', 129.0756, 35.1796],
  ['런던', -0.1276, 51.5072],
])('서울 밖 %s 위치는 이동 좌표를 반환하지 않음', async (_, longitude, latitude) => {
  await expect(seoulLocation(city, { longitude, latitude })).rejects.toMatchObject({
    kind: 'OUTSIDE_SEOUL',
  });
});

test('서울 사각 범위 안의 광명도 실제 구 경계 밖이면 거부', async () => {
  const [x, y] = [-10095.394971251895, -9862.495798392454];
  expect(x).toBeGreaterThan(city.bounds[0]);
  expect(y).toBeGreaterThan(city.bounds[1]);
  expect(x).toBeLessThan(city.bounds[2]);
  expect(y).toBeLessThan(city.bounds[3]);
  await expect(
    seoulLocation(city, { longitude: 126.8647, latitude: 37.4785 })
  ).rejects.toMatchObject({ kind: 'OUTSIDE_SEOUL' });
});

test.each([
  [NaN, 37.5],
  [127, Infinity],
  [181, 37.5],
  [127, -91],
])('잘못된 좌표 %s,%s 거부', async (longitude, latitude) => {
  await expect(seoulLocation(city, { longitude, latitude })).rejects.toMatchObject({
    kind: 'UNAVAILABLE',
  });
});

test('요청 한 번에 새 위치를 조회하고 성공 후에만 이동 좌표 반환', async () => {
  const getCurrentPosition = vi.fn<Geolocation['getCurrentPosition']>((success) =>
    success({
      coords: { longitude: 126.978, latitude: 37.5665 },
    } as GeolocationPosition)
  );
  const result = await currentLocation(city, { getCurrentPosition }, true);
  expect(result.districtName).toBe('중구');
  expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  expect(getCurrentPosition.mock.calls[0][2]).toEqual({
    enableHighAccuracy: true,
    maximumAge: 0,
    timeout: 15000,
  });
});

test.each([
  [1, 'DENIED'],
  [2, 'UNAVAILABLE'],
  [3, 'TIMEOUT'],
])('위치 조회 오류 %s를 사용자 안내 %s로 구분', async (code, kind) => {
  const getCurrentPosition: Geolocation['getCurrentPosition'] = (_, failure) =>
    failure?.({ code } as GeolocationPositionError);
  await expect(currentLocation(city, { getCurrentPosition }, true)).rejects.toMatchObject({ kind });
});

test('보안 연결과 지원 여부를 검사하고 내부 오류 내용 비노출', async () => {
  const getCurrentPosition = vi.fn(() => {
    throw new Error('internal-secret');
  });
  await expect(currentLocation(city, { getCurrentPosition }, false)).rejects.toMatchObject({
    kind: 'INSECURE',
  });
  expect(getCurrentPosition).not.toHaveBeenCalled();
  await expect(currentLocation(city, undefined, true)).rejects.toMatchObject({
    kind: 'UNSUPPORTED',
  });
  await expect(currentLocation(city, { getCurrentPosition }, true)).rejects.toMatchObject({
    kind: 'FAILED',
    message: '현재 위치로 이동하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  });
});
