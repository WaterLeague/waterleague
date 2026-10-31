import type { SharedInstallation } from '../entity/installation';

export function countInstallations(installations: Pick<SharedInstallation, 'districtId'>[]) {
  const counts: Record<string, number> = {};
  for (const installation of installations)
    counts[installation.districtId] = (counts[installation.districtId] ?? 0) + 1;
  return counts;
}

export function installationCountLabel(
  counts: Record<string, number> | null,
  districtId: string,
  error = ''
) {
  if (counts === null) return error ? '시설 확인 실패' : '시설 불러오는 중';
  return `시설 ${counts[districtId] ?? 0}개`;
}
