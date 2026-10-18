import { expect, it } from 'vitest';
import fixture from '../view/fixtures/catalog.json';
import { watershedCatalogDto, type NetworkPlacement } from '../dto/watershedDto';
import { validateNetworkDesign, designFingerprint } from './watershedDesign';
const catalog = watershedCatalogDto.parse(fixture);
const first: NetworkPlacement = {
  id: 'F1',
  facilityType: 'BIORETENTION',
  catchmentId: 'S1',
  areaM2: 100,
  treatedImperviousM2: 1000,
};
it('같은 집수구역의 여러 시설이 불투수 유입을 중복 배분하는 설계 거부', () => {
  expect(validateNetworkDesign(catalog, [first])).toBe('');
  const second = { ...first, id: 'F2', treatedImperviousM2: 27500 };
  expect(validateNetworkDesign(catalog, [first, second])).toContain('중복 유입');
  expect(validateNetworkDesign(catalog, [first, { ...second, catchmentId: 'S2' }])).toBe('');
});
it('0·소수 과다·결측·미등록 집수구역·동일 식별자 거부', () => {
  for (const areaM2 of [0, 0.001, NaN, Infinity, -1])
    expect(validateNetworkDesign(catalog, [{ ...first, areaM2 }])).not.toBe('');
  expect(validateNetworkDesign(catalog, [{ ...first, areaM2: 0.01, treatedImperviousM2: 0 }])).toBe(
    ''
  );
  expect(validateNetworkDesign(catalog, [{ ...first, catchmentId: 'S999' }])).not.toBe('');
  expect(validateNetworkDesign(catalog, [first, { ...first, id: 'f1' }])).not.toBe('');
});
it('소수 합산 경계와 전체 불투수 대체를 제한한 관망 조건 유지', () => {
  const limited = structuredClone(catalog);
  limited.catalog.catchments[0] = { id: 'S1', areaM2: 1, imperviousM2: 0.3, outletNodeId: 'J4' };
  expect(
    validateNetworkDesign(limited, [{ ...first, areaM2: 0.1, treatedImperviousM2: 0.2 }])
  ).toBe('');
  expect(
    validateNetworkDesign(catalog, [
      { ...first, catchmentId: 'S9', areaM2: 13729.38, treatedImperviousM2: 0 },
    ])
  ).toContain('초과');
});
it('동일 설계 재시도와 면적·카탈로그 변경을 구분한 요청 기준', () => {
  const second = { ...first, id: 'F2', catchmentId: 'S2' };
  expect(designFingerprint('a', [first, second])).toBe(designFingerprint('a', [second, first]));
  expect(designFingerprint('a', [first])).not.toBe(
    designFingerprint('a', [{ ...first, treatedImperviousM2: 0 }])
  );
  expect(designFingerprint('a', [first])).not.toBe(designFingerprint('b', [first]));
});
