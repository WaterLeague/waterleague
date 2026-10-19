import type { SiteQuery } from '../repository/installationRepository';

export function mapSiteQuery(query: SiteQuery): SiteQuery {
  // 목록 필터·페이지와 무관한 주변 후보를 지도에 남긴다.
  return {
    districtId: query.districtId,
    x: query.x,
    y: query.y,
    offset: 0,
    type: '',
    vacant: false,
    surface: '',
  };
}
