import type { WatershedCatalog } from '../dto/watershedDto';
import type { StoragePlacement } from '../dto/storageDto';
import type { PumpPlacement } from '../dto/pumpDto';
export function pumpNodes(catalog: WatershedCatalog, tanks: StoragePlacement[]) {
  const nodes = new Map<string, { id: string; invertM: number; maxDepthM: number }>();
  for (const c of catalog.storageCatalog?.connections ?? [])
    for (const n of [c.inlet, c.receiver]) nodes.set(n.id, n);
  const targets = [...nodes.values()];
  for (const t of tanks)
    nodes.set('WLST_' + t.id, { id: 'WLST_' + t.id, invertM: t.invertM, maxDepthM: t.depthM });
  return { sources: [...nodes.values()], targets };
}
export function pumpReceivers(catalog: WatershedCatalog, tanks: StoragePlacement[], from: string) {
  const graph = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    if (!graph.has(a)) graph.set(a, new Set());
    graph.get(a)!.add(b);
  };
  for (const l of catalog.layout?.links ?? []) add(l.fromNode, l.toNode);
  for (const t of tanks) {
    const c = catalog.storageCatalog?.connections.find((c) => c.id === t.connectionId);
    if (c) {
      add(c.inlet.id, 'WLST_' + t.id);
      add('WLST_' + t.id, c.receiver.id);
    }
  }
  const seen = new Set([from]),
    queue = [from];
  while (queue.length)
    for (const n of graph.get(queue.shift()!) ?? [])
      if (!seen.has(n)) {
        seen.add(n);
        queue.push(n);
      }
  return pumpNodes(catalog, tanks).targets.filter((n) => n.id !== from && seen.has(n.id));
}
export function validatePumps(
  catalog: WatershedCatalog,
  tanks: StoragePlacement[],
  pumps: PumpPlacement[],
  ids: Set<string>
) {
  const nodes = pumpNodes(catalog, tanks).sources,
    pairs = new Set<string>();
  if (pumps.length && (!catalog.pumpCatalog || !catalog.pumpCatalogHash))
    return '펌프 성능자료를 다시 조회해 주세요.';
  for (const p of pumps) {
    const source = nodes.find((n) => n.id === p.fromNode),
      pair = p.fromNode + '\n' + p.toNode;
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,23}$/.test(p.id) || ids.has(p.id.toUpperCase()))
      return '시설 식별자가 중복되거나 올바르지 않습니다.';
    ids.add(p.id.toUpperCase());
    if (!source || !pumpReceivers(catalog, tanks, p.fromNode).some((n) => n.id === p.toNode))
      return '펌프의 흡입 지점과 연결된 하류 지점을 선택해 주세요. 삭제한 저류조에는 연결할 수 없습니다.';
    if (pairs.has(pair)) return '같은 흡입·토출 연결의 펌프 설계가 이미 있습니다.';
    pairs.add(pair);
    const d = p.delivery;
    const quantities: [number, number, number][] = [
      [p.startDepthM, 0.001, Math.min(100, source.maxDepthM)],
      [p.stopDepthM, 0.001, 100],
      [d.lengthM, 0.001, 10000],
      [d.diameterM, 0.001, 20],
      [d.roughnessMm, 0.001, 100],
      [d.pressureHeadLimitM, 0.001, 1000],
      [d.entranceLoss, 0, 100],
      [d.exitLoss, 0, 100],
      [d.averageLoss, 0, 100],
    ];
    if (
      quantities.some(
        ([v, min, max]) =>
          !Number.isFinite(v) ||
          v < min ||
          v > max ||
          Math.abs(v * 1000 - Math.round(v * 1000)) > 1e-6
      )
    )
      return '펌프 수위·압력관 제원을 허용 범위 안에서 소수 셋째 자리까지 입력해 주세요.';
    if (p.startDepthM <= p.stopDepthM) return '기동 수심은 정지 수심보다 높아야 합니다.';
    if (d.pressureHeadLimitM <= d.diameterM || d.roughnessMm >= d.diameterM * 1000)
      return '관경·절대조도·허용 압력수두를 확인해 주세요.';
    if (!['ON', 'OFF'].includes(p.initialStatus) || typeof d.checkValve !== 'boolean')
      return '펌프 초기 상태와 역류방지판을 확인해 주세요.';
  }
  return '';
}
