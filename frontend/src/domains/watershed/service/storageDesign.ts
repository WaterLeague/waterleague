import type { PumpPlacement } from '../dto/pumpDto';
import { validatePumps } from './pumpDesign';
import type { ConduitPlacement } from '../dto/conduitDto';
import { validateConduits } from './conduitDesign';
import type { NetworkPlacement, WatershedCatalog } from '../dto/watershedDto';
import type { StoragePlacement } from '../dto/storageDto';
import { validateNetworkDesign } from './watershedDesign';
const precision = (value: number, digits: number) =>
  Number.isFinite(value) &&
  Math.abs(value * 10 ** digits - Math.round(value * 10 ** digits)) < 1e-6;
export function validateCombinedDesign(
  catalog: WatershedCatalog,
  lids: NetworkPlacement[],
  tanks: StoragePlacement[],
  conduits: ConduitPlacement[] = [],
  pumps: PumpPlacement[] = []
) {
  if (lids.length) {
    const error = validateNetworkDesign(catalog, lids);
    if (error) return error;
  }
  if (!lids.length && !tanks.length && !conduits.length && !pumps.length)
    return '시설을 한 곳 이상 설계에 추가해 주세요.';
  if (lids.length + tanks.length + conduits.length + pumps.length > 20)
    return '한 설계에는 최대 20곳까지 추가할 수 있습니다.';
  const ids = new Set(lids.map((p) => p.id.toUpperCase()));
  for (const t of tanks) {
    if (ids.has(t.id.toUpperCase()) || !/^[A-Za-z][A-Za-z0-9_-]{0,23}$/.test(t.id))
      return '시설 식별자가 중복되거나 올바르지 않습니다.';
    ids.add(t.id.toUpperCase());
    const c = catalog.storageCatalog?.connections.find((c) => c.id === t.connectionId);
    if (!c || !catalog.storageCatalogHash) return '공개 관망의 저류조 연결을 확인해 주세요.';
    if (
      ![t.areaM2, t.invertM, t.depthM, t.initialDepthM].every(Number.isFinite) ||
      t.areaM2 < 0.01 ||
      t.areaM2 > 1e6 ||
      t.invertM < -1000 ||
      t.invertM > 10000 ||
      t.depthM <= 0 ||
      t.depthM > 100 ||
      t.initialDepthM < 0 ||
      t.initialDepthM > t.depthM
    )
      return '저류조 면적·높이·초기 수심을 확인해 주세요.';
    if (
      !precision(t.areaM2, 2) ||
      ![t.invertM, t.depthM, t.initialDepthM].every((v) => precision(v, 3))
    )
      return '면적은 소수 둘째 자리, 높이는 소수 셋째 자리까지 입력해 주세요.';
    for (const kind of ['inlet', 'drain', 'overflow'] as const) {
      const p = t[kind],
        n = kind === 'inlet' ? c.inlet : c.receiver;
      if (
        ![p.crestM, p.diameterM, p.dischargeCoefficient].every(Number.isFinite) ||
        p.diameterM < 0.001 ||
        p.diameterM > 100 ||
        p.dischargeCoefficient < 0.001 ||
        p.dischargeCoefficient > 1 ||
        p.crestM < -1000 ||
        p.crestM > 10000 ||
        ![p.crestM, p.diameterM, p.dischargeCoefficient].every((v) => precision(v, 3)) ||
        p.crestM < Math.max(t.invertM, n.invertM) ||
        p.crestM + p.diameterM > Math.min(t.invertM + t.depthM, n.invertM + n.maxDepthM) + 1e-9
      )
        return '개구부 전체가 저류조와 연결 절점의 바닥·상단 사이에 들어가야 합니다.';
    }
    if (t.overflow.crestM <= t.drain.crestM) return '비상 배수구는 일반 배수구보다 높아야 합니다.';
  }
  return validateConduits(catalog, conduits, ids) || validatePumps(catalog, tanks, pumps, ids);
}
