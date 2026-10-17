import { traceCatalogDto, traceTileDto } from '../dto/floodTraceDto';
import type { TraceCatalog, TraceTile, TraceTileIndex } from '../entity/floodTrace';
import { FloodTraceError } from '../exception/FloodTraceError';

const base = '/api/v1/flood-traces/seoul-flood-traces-20261018-v1';
let catalog: Promise<TraceCatalog> | undefined;
const tiles = new Map<string, Promise<TraceTile>>();
export function loadTraceCatalog() {
  catalog ??= fetch(base + '/catalog', { cache: 'force-cache', credentials: 'omit' })
    .then(async (r) => {
      if (!r.ok) throw new FloodTraceError();
      return traceCatalogDto.parse(await r.json()).catalog;
    })
    .catch(() => {
      catalog = undefined;
      throw new FloodTraceError();
    });
  return catalog;
}
export function loadTraceTile(eventId: string, tile: TraceTileIndex): Promise<TraceTile> {
  const key = `${eventId}/${tile.id}`;
  const cached = tiles.get(key);
  if (cached) return cached;
  const pending = fetch(`${base}/${encodeURIComponent(eventId)}/${encodeURIComponent(tile.id)}`, {
    cache: 'force-cache',
    credentials: 'omit',
  })
    .then(async (r) => {
      if (!r.ok) throw new FloodTraceError();
      const bytes = await r.arrayBuffer();
      if (bytes.byteLength !== tile.bytes) throw new FloodTraceError();
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
      if (hash !== tile.sha256) throw new FloodTraceError();
      const result = traceTileDto.parse(JSON.parse(new TextDecoder().decode(bytes)));
      if (result.eventId !== eventId || result.id !== tile.id) throw new FloodTraceError();
      return result;
    })
    .catch(() => {
      tiles.delete(key);
      throw new FloodTraceError();
    });
  tiles.set(key, pending);
  if (tiles.size > 80) tiles.delete(tiles.keys().next().value!);
  return pending;
}
