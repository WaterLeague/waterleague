import { api } from '../../../shared/repository/apiClient';
import { GameDataError } from '../../game/exception/GameDataError';
import { disasterCatalogDto } from '../dto/disasterDto';
export async function loadDisasters() {
  const parsed = disasterCatalogDto.safeParse(await api<unknown>('/disasters'));
  if (!parsed.success) throw new GameDataError();
  for (const e of parsed.data.events) {
    if (new Set(e.regions.map((r) => r.districtId)).size !== e.regions.length)
      throw new GameDataError();
    const first = e.regions[0];
    for (const r of e.regions) {
      if (
        r.start !== first.start ||
        r.end !== first.end ||
        Date.parse(r.end) - Date.parse(r.start) !== r.depthsMm.length * 60000 ||
        Math.abs(r.totalDepthMm - r.depthsMm.reduce((a, b) => a + b, 0)) > 0.001
      )
        throw new GameDataError();
    }
  }
  return parsed.data;
}
