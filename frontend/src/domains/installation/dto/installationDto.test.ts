import { expect, test } from 'vitest';
import actual from '../__tests__/fixtures/nativeInfiltrationSite.json';
import { siteDto, sitePageDto } from './installationDto';

test('실제 원형 지상 응답의 문헌 참조 침투 경계를 목록·상세에서 보존', () => {
  const site = siteDto.parse(actual);
  const page = sitePageDto.parse({
    sites: [actual],
    districtCounts: { [actual.districtId]: 1 },
    matchedCount: 1,
    offset: 0,
    limit: 200,
  });
  expect(page.sites[0]).toEqual(site);
  for (const boundary of [
    site.physicalInputs?.rainGardenBoundary,
    site.physicalInputs?.bioretentionBoundary,
    site.physicalInputs?.trenchBoundary,
  ]) {
    expect(boundary?.basis).toBe('PUBLIC_REFERENCE_SCENARIO_NOT_LOCAL_MEASUREMENT');
    expect(boundary?.seepageMmH).toBe(3.302);
  }
  expect(site.allowedTypes).toEqual([
    'RAIN_GARDEN',
    'BIORETENTION',
    'VEGETATIVE_SWALE',
    'INFILTRATION_TRENCH',
  ]);
});

test('미등록 침투 근거와 음수 침투율 거부', () => {
  for (const replacement of [{ basis: 'MEASURED' }, { seepageMmH: -1 }]) {
    const invalid = structuredClone(actual);
    Object.assign(invalid.physicalInputs.rainGardenBoundary, replacement);
    expect(siteDto.safeParse(invalid).success).toBe(false);
  }
});
