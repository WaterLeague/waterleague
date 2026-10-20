import type { SharedSite } from '../entity/installation';
import type { CisternPlanRequest } from '../dto/cisternPlanDto';
import { sitePlacementRestricted } from './siteSuitabilityService';
export type CisternSiteRole = 'roof' | 'ground';
export const cisternSiteColors = { roof: '#4badd0', ground: '#559e8d' } as const;
export function cisternSelectionError(
  site: SharedSite,
  role: CisternSiteRole,
  ownDistrict: string | null,
  occupied: boolean
) {
  if (ownDistrict && site.districtId !== ownDistrict) return '내 소속 구의 위치를 선택해 주세요.';
  if (site.kind !== (role === 'roof' ? 'ROOF' : 'GROUND'))
    return role === 'roof'
      ? '집수할 지붕 후보를 선택해 주세요.'
      : '탱크를 둘 지상 후보를 선택해 주세요.';
  if (occupied) return '이미 시설이 설치된 위치입니다. 다른 위치를 선택해 주세요.';
  if (sitePlacementRestricted(site))
    return '금지 조건 또는 미충족 안전 조건이 있는 위치입니다. 다른 위치를 선택해 주세요.';
  if (site.existingInfrastructure)
    return '공개 시설 영역과 겹치는 후보입니다. 다른 위치를 선택해 주세요.';
  return '';
}
export function cisternRequest(
  roof: SharedSite | null,
  ground: SharedSite | null,
  capture: string,
  area: string,
  depth: string
): CisternPlanRequest | null {
  const values = [capture, area, depth].map(Number);
  if (
    !roof ||
    !ground ||
    sitePlacementRestricted(roof) ||
    sitePlacementRestricted(ground) ||
    roof.districtId !== ground.districtId ||
    roof.kind !== 'ROOF' ||
    ground.kind !== 'GROUND' ||
    values.some((v) => !Number.isFinite(v) || v <= 0) ||
    values[0] > roof.maxAreaM2 ||
    values[1] > ground.maxAreaM2 ||
    values[2] > 100 ||
    !/^\d+(\.\d{1,2})?$/.test(capture) ||
    !/^\d+(\.\d{1,2})?$/.test(area) ||
    !/^\d+(\.\d{1,3})?$/.test(depth)
  )
    return null;
  return {
    districtId: roof.districtId,
    roofCellId: roof.cellId,
    groundCellId: ground.cellId,
    roofModelHash: roof.modelHash,
    groundModelHash: ground.modelHash,
    captureAreaM2: values[0],
    tankAreaM2: values[1],
    tankDepthM: values[2],
  };
}
