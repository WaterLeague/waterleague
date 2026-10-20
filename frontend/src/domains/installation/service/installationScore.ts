import type { SharedInstallation } from '../entity/installation';
import { scoreFormat } from '../../weekly/service/scoreFormat';
export function installationScore(value: Pick<SharedInstallation, 'scoreM3'>) {
  return value.scoreM3 == null
    ? '미계산 · 반영 기록 없음'
    : `${scoreFormat.format(value.scoreM3)} m³`;
}
