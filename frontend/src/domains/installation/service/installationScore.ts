import type { SharedInstallation } from '../entity/installation';
const format = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 });
export function installationScore(value: SharedInstallation) {
  return value.scoreM3 == null ? '0 m³ · 반영 기록 없음' : `${format.format(value.scoreM3)} m³`;
}
