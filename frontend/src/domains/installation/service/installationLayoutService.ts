import type { SharedInstallation, InstallationLayout } from '../entity/installation';

export function installationLayoutKey(values: SharedInstallation[]) {
  // 점수·평가 시각 갱신은 건물 분류와 시설 형상을 다시 만들지 않는다.
  const layouts: InstallationLayout[] = values.map(
    ({ id, districtId, cellId, ownerId, facilityType, areaM2 }) => ({
      id,
      districtId,
      cellId,
      ownerId,
      facilityType,
      areaM2,
    })
  );
  layouts.sort((a, b) => a.id.localeCompare(b.id));
  return JSON.stringify(layouts);
}
