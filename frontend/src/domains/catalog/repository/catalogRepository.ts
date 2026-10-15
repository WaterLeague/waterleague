import { mapDto, rainAuditDto } from '../dto/catalogDto';
import { CatalogError } from '../exception/CatalogError';
import { toCandidateMap } from '../mapper/catalogMapper';
async function read(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new CatalogError('NETWORK');
  return response.json();
}
export async function loadCatalog(signal: AbortSignal) {
  const [mapData, rainData] = await Promise.all([
    read('/data/seongsu.json', signal),
    read('/data/rainfall-audit.json', signal),
  ]);
  const map = mapDto.safeParse(mapData),
    rain = rainAuditDto.safeParse(rainData);
  if (!map.success || !rain.success) throw new CatalogError('INVALID_DATA');
  return { map: toCandidateMap(map.data), rainfall: rain.data };
}
