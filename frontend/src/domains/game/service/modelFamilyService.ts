import type { RainfallCatalog, RainfallUse } from '../entity/game';
export function sameMapModels(catalog: RainfallCatalog | null, hash: string | undefined) {
  const source = catalog?.models.find((m) => m.modelHash === hash);
  if (!source) return [];
  return catalog!.models
    .filter((m) => (m.mapId ?? 'legacy') === (source.mapId ?? 'legacy'))
    .sort(
      (a, b) =>
        Number(b.regionalRainfallUse === 'NEAREST_AWS_OBSERVED_REPLAY') -
        Number(a.regionalRainfallUse === 'NEAREST_AWS_OBSERVED_REPLAY')
    );
}

export function rainfallLabel(use?: RainfallUse) {
  return use === 'NEAREST_AWS_OBSERVED_REPLAY'
    ? '인근 관측 강우'
    : use === 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION'
      ? '공통 비교 강우'
      : '관측 강우';
}
export function rainfallNote(use?: RainfallUse) {
  return use === 'NEAREST_AWS_OBSERVED_REPLAY'
    ? '가장 가까운 AWS 관측 강우 재생 · 블록 강우 대표성 미검증'
    : use === 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION'
      ? '성동 관측 강우 공통 재생 · 지역 실측 강우 아님'
      : '기상청 실제 관측 · 선택한 조건으로 계산·순위 구분';
}
