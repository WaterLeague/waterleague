import type { WatershedCatalog } from '../dto/watershedDto';
import type { ConduitGeometry, ConduitPlacement } from '../dto/conduitDto';
const precision = (n: number, digits: number) =>
  Number.isFinite(n) && Math.abs(n * 10 ** digits - Math.round(n * 10 ** digits)) < 1e-6;
export function conduitDimensions(p: ConduitGeometry) {
  return `${p.shape === 'CIRCULAR' ? `원형 내경 ${p.fullDepthM} m` : `폐합 높이 ${p.fullDepthM} × 폭 ${p.widthM} m`} · 병렬 ${p.barrels}개 · 조도 ${p.roughness}`;
}
export function validateConduits(
  catalog: WatershedCatalog,
  placements: ConduitPlacement[],
  ids: Set<string>
) {
  const seen = new Set<string>();
  for (const p of placements) {
    if (
      !catalog.conduitCatalogHash ||
      !catalog.conduitCatalog?.conduits.some((c) => c.id === p.conduitId)
    )
      return '공개 원 관로를 선택해 주세요.';
    if (
      seen.has(p.conduitId) ||
      ids.has(p.id.toUpperCase()) ||
      !/^[A-Za-z][A-Za-z0-9_-]{0,23}$/.test(p.id)
    )
      return '같은 관로 또는 시설 식별자를 중복 변경할 수 없습니다.';
    const source = catalog.conduitCatalog!.conduits.find((c) => c.id === p.conduitId)!;
    if (p.fullDepthM > source.maxFullDepthM)
      return `관로 높이는 공개 접속 절점 범위 ${source.maxFullDepthM} m 이하여야 합니다. 현장 허가 한도와는 구분합니다.`;
    seen.add(p.conduitId);
    ids.add(p.id.toUpperCase());
    if (
      !['CIRCULAR', 'RECT_CLOSED'].includes(p.shape) ||
      !precision(p.fullDepthM, 3) ||
      p.fullDepthM < 0.01 ||
      p.fullDepthM > 100 ||
      (p.shape === 'CIRCULAR'
        ? p.widthM !== null
        : p.widthM === null || !precision(p.widthM, 3) || p.widthM < 0.01 || p.widthM > 100) ||
      !Number.isInteger(p.barrels) ||
      p.barrels < 1 ||
      p.barrels > 20 ||
      !precision(p.roughness, 4) ||
      p.roughness < 0.001 ||
      p.roughness > 1
    )
      return '관로 치수·개수·조도를 확인해 주세요. 치수는 소수 셋째, 조도는 넷째 자리까지 지원합니다.';
  }
  return '';
}
