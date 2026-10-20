import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalog from '../../../../../backend/src/main/resources/facilities/epa-designs-v1.json';
import currentCatalog from '../../../../../backend/src/main/resources/facilities/epa-designs-v4.json';
import actualSite from '../../installation/__tests__/fixtures/nativeInfiltrationSite.json';
import { siteDto } from '../../installation/dto/installationDto';
import { facilityCatalogDto, facilityEvidenceDto } from '../dto/facilityDto';
import { FacilityProfileEvidence } from './FacilityProfileEvidence';

it('공개 제원 원본의 값·문헌 범위·가정과 보관 해시 표시', () => {
  const parsed = facilityCatalogDto.parse(catalog);
  const archived = facilityEvidenceDto.parse({
    ...parsed,
    profile: parsed.profiles.GREEN_ROOF,
    catalogSha256: 'a'.repeat(64),
  });
  const markup = renderToStaticMarkup(<FacilityProfileEvidence {...archived} />);
  expect(markup).toContain('이 계산 결과에 보관된 설계 제원');
  expect(markup).toContain('150 mm');
  expect(markup).toContain('문헌 범위에서 선택한 설계값');
  expect(markup).toContain('즉시 월류 설계 조건');
  expect(
    renderToStaticMarkup(
      <FacilityProfileEvidence {...archived} profile={parsed.profiles.PERMEABLE_PAVEMENT} />
    )
  ).toContain('실측 미확보 설계 가정');
  expect(markup).toContain(archived.catalogSha256);
  expect(markup).toContain(archived.source.sha256);
  expect(markup).not.toContain('data/private');
  expect(facilityEvidenceDto.safeParse({ ...archived, catalogSha256: 'invalid' }).success).toBe(
    false
  );
});

it('계산 당시 원지반 경계와 이전 입력의 침투 미연결 구분', () => {
  const parsed = facilityCatalogDto.parse(catalog);
  const archived = facilityEvidenceDto.parse({
    ...parsed,
    profile: parsed.profiles.RAIN_GARDEN,
    catalogSha256: 'b'.repeat(64),
    nativeSoilBoundary: {
      method: 'RG_NATIVE_SOIL_SEEPAGE_V1',
      seepageMmH: 3.302,
      basis: 'TEXTURE_CLASS_LITERATURE_ESTIMATE',
      liner: 'UNLINED_DESIGN_NOT_SITE_CONFIRMED',
      storageThicknessMm: 0,
    },
  });
  const current = renderToStaticMarkup(<FacilityProfileEvidence {...archived} />);
  expect(current).toContain('3.302 mm/h');
  expect(current).toContain('공개 토성군·문헌 추정');
  expect(current).not.toContain('침투량을 0으로');
  const previous = renderToStaticMarkup(
    <FacilityProfileEvidence {...archived} nativeSoilBoundary={undefined} />
  );
  expect(previous).toContain('침투량을 0으로');
  expect(previous).not.toContain('3.302 mm/h');
});

it('실제 원형 후보의 세 침투 시설에 공통 문헌 토양 근거 표시', () => {
  const site = siteDto.parse(actualSite);
  const parsed = facilityCatalogDto.parse(currentCatalog);
  const boundaries = [
    ['RAIN_GARDEN', site.physicalInputs?.rainGardenBoundary],
    ['BIORETENTION', site.physicalInputs?.bioretentionBoundary],
    ['INFILTRATION_TRENCH', site.physicalInputs?.trenchBoundary],
  ] as const;
  for (const [facility, nativeSoilBoundary] of boundaries) {
    const evidence = facilityEvidenceDto.parse({
      ...parsed,
      profile: parsed.profiles[facility],
      catalogSha256: 'c'.repeat(64),
      nativeSoilBoundary,
    });
    const markup = renderToStaticMarkup(<FacilityProfileEvidence {...evidence} />);
    expect(markup).toContain('3.302 mm/h');
    expect(markup).toContain('공통 문헌 토양 조건·현장 실측 아님');
    expect(markup).not.toContain('토성 미확보·설계 가정');
    expect(markup).not.toContain('공개 토성군·문헌 추정');
  }
});
