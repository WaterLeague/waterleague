import type { NetworkPlacement, WatershedCatalog } from '../dto/watershedDto';
export const networkNames = {
  BIORETENTION: '생물저류시설',
  INFILTRATION_TRENCH: '침투 트렌치',
  VEGETATIVE_SWALE: '식생수로',
  RAINWATER_CISTERN: '빗물이용조',
} as const;
export function validateNetworkDesign(catalog: WatershedCatalog, placements: NetworkPlacement[]) {
  if (!placements.length) return '시설을 한 곳 이상 설계에 추가해 주세요.';
  if (placements.length > 20) return '한 설계에는 최대 20곳까지 추가할 수 있습니다.';
  const ids = new Set<string>();
  const grouped = new Map<string, { area: number; treated: number }>();
  for (const p of placements) {
    if (ids.has(p.id.toUpperCase()) || !/^[A-Za-z][A-Za-z0-9_-]{0,23}$/.test(p.id))
      return '시설 식별자가 중복되거나 올바르지 않습니다.';
    ids.add(p.id.toUpperCase());
    if (
      !catalog.catalog.templates[p.facilityType] ||
      !catalog.catalog.catchments.some((c) => c.id === p.catchmentId)
    )
      return '공개 관망에 없는 시설 또는 집수구역입니다.';
    if (
      ![p.areaM2, p.treatedImperviousM2].every(
        (v) =>
          Number.isFinite(v) && v >= 0 && v <= 1e6 && Math.abs(v * 100 - Math.round(v * 100)) < 1e-6
      ) ||
      p.areaM2 < 0.01
    )
      return '시설 면적은 0.01 m² 이상, 처리 면적은 0 m² 이상으로 소수 둘째 자리까지 입력해 주세요.';
    const current = grouped.get(p.catchmentId) ?? { area: 0, treated: 0 };
    // 소수 면적의 합산 오차가 사용 가능 면적 판정을 바꾸지 않도록 정수 단위로 집계한다.
    current.area += Math.round(p.areaM2 * 100);
    current.treated += Math.round(p.treatedImperviousM2 * 100);
    grouped.set(p.catchmentId, current);
  }
  for (const [id, sum] of grouped) {
    const c = catalog.catalog.catchments.find((c) => c.id === id)!;
    if (sum.area / 100 > Math.min(c.imperviousM2, c.areaM2 * 0.999))
      return `${id}의 대체 가능한 불투수 면적을 초과했습니다.`;
    if ((sum.area + sum.treated) / 100 > c.imperviousM2)
      return `${id}의 남은 불투수 면적을 초과하여 빗물을 중복 유입할 수 없습니다.`;
  }
  return '';
}
export const designFingerprint = (hash: string, placements: NetworkPlacement[]) =>
  JSON.stringify([
    hash,
    [...placements]
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((p) => [p.id, p.catchmentId, p.facilityType, p.areaM2, p.treatedImperviousM2]),
  ]);
