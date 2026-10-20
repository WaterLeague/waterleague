import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalog from '../../../../../backend/src/main/resources/facilities/epa-designs-v4.json';
import actualSite from '../../installation/__tests__/fixtures/nativeInfiltrationSite.json';
import { siteDto } from '../../installation/dto/installationDto';
import { facilityCatalogDto } from '../dto/facilityDto';
import { FacilityDesignEvidence } from './FacilityDesignEvidence';

vi.mock('../controller/useFacilityCatalog', () => ({
  useFacilityCatalog: () => ({ catalog: facilityCatalogDto.parse(catalog), failed: false }),
}));

it('실제 원형 후보의 식생수로 경사를 공통 문헌 조건으로 표시', () => {
  const site = siteDto.parse(actualSite);
  const markup = renderToStaticMarkup(
    <FacilityDesignEvidence site={site} type="VEGETATIVE_SWALE" />
  );
  expect(markup).toContain('경사는 공통 문헌 설계 조건이며 실제 수로 종단 측량값이 아닙니다.');
  expect(markup).not.toContain('경사는 공개 DEM의 지역 대용값');
});

it('기존 지형 대용 경사 근거 보존', () => {
  const input = structuredClone(actualSite);
  input.physicalInputs.swaleDesign.slopeBasis = 'REGIONAL_TERRAIN_PROXY_NOT_LONGITUDINAL_SURVEY';
  const markup = renderToStaticMarkup(
    <FacilityDesignEvidence site={siteDto.parse(input)} type="VEGETATIVE_SWALE" />
  );
  expect(markup).toContain('경사는 공개 DEM의 지역 대용값이며 실제 수로 종단 측량값이 아닙니다.');
  expect(markup).not.toContain('경사는 공통 문헌 설계 조건');
});
