import type { WatershedCatalog, NetworkPlacement } from '../dto/watershedDto';
import { cisternCostSnapshotDto } from '../dto/cisternCostDto';
export function previewCisternCosts(catalog: WatershedCatalog, placements: NetworkPlacement[]) {
  const source = catalog.cisternCostCatalog,
    hash = catalog.cisternCostCatalogHash;
  if (!source || !hash) return null;
  const cisterns = placements.filter((p) => p.facilityType === 'RAINWATER_CISTERN');
  if (!cisterns.length) return null;
  const depth = catalog.catalog.templates.RAINWATER_CISTERN.parameters.storageDepthMm;
  if (typeof depth !== 'number' || !Number.isInteger(depth)) return null;
  const items = [...cisterns]
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((p) => {
      // 면적 소수 둘째 자리와 mm 제원을 정수로 환산하여 용량의 정수배만 허용한다.
      const scaled = Math.round(p.areaM2 * 100) * depth;
      const units =
        scaled % 235000 === 0 && scaled / 235000 >= 1 && scaled / 235000 <= 256
          ? scaled / 235000
          : null;
      return {
        placementId: p.id,
        capacityM3: (p.areaM2 * depth) / 1000,
        equivalentUnits: units,
        status: units === null ? 'CAPACITY_NOT_MATCHED' : 'CAPACITY_EQUIVALENT_ONLY',
        quotes:
          units === null
            ? []
            : source.quotes.map((q) => {
                const total = q.totalKrw * units;
                const annual = Object.fromEntries(
                  source.annualOperation.ratesOnInitialCost.map((r) => [
                    r.id,
                    Math.round(total * Number(r.rate)),
                  ])
                );
                annual.CLEANING =
                  (source.annualOperation.cleaning.costKrw * units) /
                  source.annualOperation.cleaning.households;
                return {
                  id: q.id,
                  quotedSubtotalKrw: total,
                  materialsKrw: q.materialsKrw * units,
                  components: Object.fromEntries(
                    Object.entries(q.components).map(([k, v]) => [k, v === null ? null : v * units])
                  ),
                  unclassifiedDifferenceKrw: (q.totalKrw - q.materialsKrw) * units,
                  annualComponentsKrw: annual,
                  annualEstimateKrw: Object.values(annual).reduce((s, v) => s + v, 0),
                };
              }),
      };
    });
  return cisternCostSnapshotDto.parse({
    schemaVersion: 1,
    catalogHash: hash,
    method: 'CAPACITY_EQUIVALENT_QUOTES_NOT_ASSEMBLY_MATCH_V1',
    unitCapacityM3: 2.35,
    items,
    source: source.source,
    limitations: source.limitations,
    completeInstalledCostKrw: null,
    budgetChargedKrw: null,
  });
}
