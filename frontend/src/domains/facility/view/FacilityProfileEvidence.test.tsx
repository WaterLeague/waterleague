import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalog from '../../../../../backend/src/main/resources/facilities/epa-designs-v1.json';
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
