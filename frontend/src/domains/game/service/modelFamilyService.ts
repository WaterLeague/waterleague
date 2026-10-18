import type { RainfallCatalog } from '../entity/game';
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
