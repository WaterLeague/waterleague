import { z } from 'zod';
import { mapDto, rainAuditDto } from '../dto/catalogDto';
import { CatalogError } from '../exception/CatalogError';
import { toCandidateMap } from '../mapper/catalogMapper';
const registryDto = z.object({
  schemaVersion: z.literal(1),
  maps: z
    .array(
      z.object({
        id: z.string(),
        file: z.string().regex(/^[a-z0-9-]+\.json$/),
        sha256: z.string().regex(/^[a-f0-9]{64}$/),
        modelHashes: z.array(z.string().regex(/^[a-f0-9]{64}$/)).min(1),
      })
    )
    .min(1)
    .max(20),
});
async function read(path: string, signal: AbortSignal, expectedHash?: string): Promise<unknown> {
  const response = await fetch(path, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new CatalogError('NETWORK');
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > 2 * 1024 * 1024) throw new CatalogError('INVALID_DATA');
  if (expectedHash) {
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    if (hash !== expectedHash) throw new CatalogError('INVALID_DATA');
  }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
async function readCatalog(signal: AbortSignal) {
  const [registryData, rainData] = await Promise.all([
    read('/data/maps.json', signal),
    read('/data/rainfall-audit.json', signal),
  ]);
  const registry = registryDto.parse(registryData);
  const bindings = registry.maps.flatMap((m) => m.modelHashes);
  if (
    new Set(bindings).size !== bindings.length ||
    new Set(registry.maps.map((m) => m.id)).size !== registry.maps.length
  )
    throw new CatalogError('INVALID_DATA');
  const maps = await Promise.all(
    registry.maps.map(async (entry) => {
      const snapshot = mapDto.parse(await read('/data/' + entry.file, signal, entry.sha256));
      if (entry.id !== snapshot.id) throw new CatalogError('INVALID_DATA');
      return { ...entry, map: toCandidateMap(snapshot) };
    })
  );
  const legacy = maps.find((m) => m.file === 'seongsu.json');
  if (!legacy) throw new CatalogError('INVALID_DATA');
  return { maps, map: legacy.map, rainfall: rainAuditDto.parse(rainData) };
}

export async function loadCatalog(signal: AbortSignal) {
  try {
    return await readCatalog(signal);
  } catch (error) {
    if (signal.aborted || error instanceof CatalogError) throw error;
    throw new CatalogError('INVALID_DATA');
  }
}
