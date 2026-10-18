import type { NetworkPlacement, WatershedCatalog } from '../dto/watershedDto';
import type { WatershedCostSnapshot } from '../dto/watershedCostDto';

export function previewWatershedCosts(
  catalog: WatershedCatalog,
  placements: NetworkPlacement[]
): WatershedCostSnapshot | null {
  const { costCatalog: cost, costCatalogHash } = catalog;
  if (!cost || !costCatalogHash || !placements.length) return null;
  const items = [...placements]
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((p) => {
      const quote = cost.entries[p.facilityType];
      const priced =
        quote?.status === 'AREA_REFERENCE_ONLY' &&
        quote.unit === 'M2' &&
        quote.unitPriceKrw != null;
      // 서버와 같은 0.01m² 정수 수량으로 원 단위 반올림을 맞춘다.
      const amount = priced
        ? Number((BigInt(Math.round(p.areaM2 * 100)) * BigInt(quote.unitPriceKrw!) + 50n) / 100n)
        : null;
      return {
        placementId: p.id,
        facilityType: p.facilityType,
        areaM2: p.areaM2,
        status: priced ? ('AREA_REFERENCE_ONLY' as const) : ('UNPRICED' as const),
        referenceAmountKrw: amount,
        notes: quote?.notes ?? ['공개 단가 미확보'],
      };
    });
  const priced = items.filter((i) => i.referenceAmountKrw !== null);
  return {
    schemaVersion: 1,
    catalogHash: costCatalogHash,
    classification: cost.classification,
    source: cost.source,
    limitations: cost.limitations,
    items,
    knownReferenceSubtotalKrw: priced.length
      ? priced.reduce((s, i) => s + i.referenceAmountKrw!, 0)
      : null,
    unpricedPlacementIds: items
      .filter((i) => i.referenceAmountKrw === null)
      .map((i) => i.placementId),
    completeInstalledCostKrw: null,
    budgetChargedKrw: null,
  };
}
