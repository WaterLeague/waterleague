import type { CisternPlacement } from '../dto/cisternDto';
import type { WatershedCatalog, NetworkPlacement } from '../dto/watershedDto';
export function cisternCatchments(catalog: WatershedCatalog) {
  const nodes = new Map(
    catalog.storageCatalog?.connections.flatMap(
      (c) =>
        [
          [c.inlet.id, c.inlet],
          [c.receiver.id, c.receiver],
        ] as const
    )
  );
  return catalog.catalog.catchments
    .filter((c) => c.areaM2 === c.imperviousM2 && nodes.has(c.outletNodeId))
    .map((c) => ({ ...c, receiver: nodes.get(c.outletNodeId)! }));
}
export function validateCistern(
  catalog: WatershedCatalog,
  p: CisternPlacement | null,
  lids: NetworkPlacement[],
  ids: Set<string>
) {
  if (!p) return '';
  const host = cisternCatchments(catalog).find((c) => c.id === p.catchmentId);
  if (!host || !catalog.storageCatalogHash)
    return '공개 원본의 전면 불투수 집수구역을 선택해 주세요.';
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,23}$/.test(p.id) || ids.has(p.id.toUpperCase()))
    return '시설 식별자가 중복되거나 올바르지 않습니다.';
  if (lids.some((l) => l.catchmentId === p.catchmentId))
    return '이용조 집수구역에 다른 시설을 중복 배분할 수 없습니다.';
  const precision = (v: number, digits: number) =>
    Number.isFinite(v) && Math.abs(v * 10 ** digits - Math.round(v * 10 ** digits)) < 1e-6;
  if (
    ![p.captureAreaM2, p.areaM2].every((v) => precision(v, 2) && v >= 0.01 && v <= 1e6) ||
    p.captureAreaM2 + p.areaM2 > host.areaM2
  )
    return '집수 면적과 덮개 면적의 합이 원 면적을 넘지 않아야 합니다.';
  if (
    ![p.invertM, p.depthM, p.initialDepthM].every((v) => precision(v, 3)) ||
    p.invertM < -1000 ||
    p.invertM > 10000 ||
    p.depthM <= 0 ||
    p.depthM > 100 ||
    p.initialDepthM < 0 ||
    p.initialDepthM > p.depthM
  )
    return '이용조의 높이·깊이·초기 수심을 입력해 주세요.';
  const n = host.receiver;
  for (const r of [p.drain, p.overflow]) {
    if (
      ![r.crestM, r.diameterM, r.dischargeCoefficient].every((v) => precision(v, 3)) ||
      r.diameterM < 0.001 ||
      r.diameterM > 100 ||
      r.dischargeCoefficient < 0.001 ||
      r.dischargeCoefficient > 1 ||
      r.crestM < -1000 ||
      r.crestM > 10000 ||
      r.crestM < Math.max(n.invertM, p.invertM) ||
      r.crestM + r.diameterM > Math.min(n.invertM + n.maxDepthM, p.invertM + p.depthM) + 1e-9
    )
      return '배수구 전체가 이용조와 연결 절점의 바닥·상단 사이에 들어가야 합니다.';
  }
  return p.overflow.crestM <= p.drain.crestM ? '비상 배수구는 일반 배수구보다 높아야 합니다.' : '';
}
