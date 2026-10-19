import type { FacilityType } from '../../game/entity/game';
import { siteKey, type SharedInstallation, type SharedSite } from '../entity/installation';
import { representativeInstallations } from './memberSitesService';
import { detailLabelDistance } from '../../city/service/cityService';

export function installationSymbols(
  installations: SharedInstallation[],
  sites: SharedSite[],
  viewerId: string | null,
  facilityType: FacilityType | '',
  distance: number
) {
  // 설치 선택 중에는 검증된 후보만 클릭 가능하며 시설 표식으로 필터를 우회하지 않는다.
  if (facilityType) return [];
  const detailed = new Set(distance < detailLabelDistance ? sites.map(siteKey) : []);
  return [...representativeInstallations(installations, viewerId).values()].filter(
    (value) => !detailed.has(siteKey(value))
  );
}
