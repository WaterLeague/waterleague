import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import rawSite from './fixtures/basinSite.json';
import { siteDto } from '../dto/installationDto';
import { FacilityPlacementPanel, type FacilityPlacementProps } from './FacilityPlacementPanel';

const site = siteDto.parse(rawSite);
const props: FacilityPlacementProps = {
  site,
  type: 'PERMEABLE_PAVEMENT',
  area: '1',
  onType: () => {},
  onArea: () => {},
  onInstall: () => {},
  districtName: '송파구',
  context: '내 소속 구',
  budget: null,
  remaining: 2_000_000_000,
  limit: 2_000_000_000,
  budgetReady: true,
  busy: false,
  canInstall: true,
};

it('주간·재해 공통 패널에서 공개 경계 교차 사유 표시와 신규 배치 폼 제외', () => {
  for (const research of [false, true]) {
    const html = renderToStaticMarkup(<FacilityPlacementPanel {...props} research={research} />);
    expect(html).toContain('공개 지도 저류 영역 · 신규 설치 제외');
    expect(html).toContain('잠실유수지');
    expect(html).toContain('교차 100 m²');
    expect(html).not.toContain('<form');
    expect(html).not.toContain('이 위치에 설치');
    expect(html).not.toContain('연구 설계에 추가');
  }
});

it('새 경계 정책과 겹치는 이전 설치도 기록 표시와 본인 철거 유지', () => {
  const html = renderToStaticMarkup(
    <FacilityPlacementPanel
      {...props}
      occupied={{
        facilityType: 'PERMEABLE_PAVEMENT',
        areaM2: 1,
        cost: 110000,
        ownerName: '내 시설',
        onRemove: () => {},
      }}
    />
  );
  expect(html).toContain('설치 완료');
  expect(html).toContain('내 시설 철거');
  expect(html).not.toContain('<form');
});
