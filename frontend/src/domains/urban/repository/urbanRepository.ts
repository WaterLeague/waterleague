import { z } from 'zod';
import { CityError } from '../../city/exception/CityError';
import type { Population, Street } from '../entity/urban';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const point = z.tuple([z.number().min(-60000).max(60000), z.number().min(-60000).max(60000)]);
const file = z.object({
  file: z.string().regex(/^(overview|tiles\/-?\d+_-?\d+)\.json$/),
  sha256: hash,
  bytes: z.number().int().positive().max(8000000),
});
const catalogDto = z.object({
  schemaVersion: z.literal(1),
  sourceSha256: hash,
  sourceDate: z.literal('2026-10-16'),
  originProjected: z.tuple([z.literal(198128), z.literal(551989)]),
  overview: file,
  tiles: z
    .array(
      file.extend({
        id: z.string(),
        bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
      })
    )
    .max(500),
  modelInput: z.literal(false),
});
const streetsDto = z.object({
  schemaVersion: z.literal(1),
  roads: z
    .array(
      z.object({
        id: z.string().regex(/^way\/\d+:\d+$/),
        class: z.string().max(30),
        districtId: z.string().max(10),
        widthM: z.number().positive().max(80),
        widthSource: z.enum(['OSM_WIDTH_TAG', 'DISPLAY_ASSUMPTION']),
        walk: z.boolean(),
        motor: z.boolean(),
        oneway: z.number().int().min(-1).max(1),
        sidewalk: z.string().max(80),
        bridge: z.boolean(),
        coordinates: z.array(point).min(2).max(30000),
      })
    )
    .max(30000),
});
export async function read(path: string, sha: string, bytes: number, signal: AbortSignal) {
  const response = await fetch(path, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new CityError('NETWORK');
  const raw = await response.arrayBuffer();
  const actual = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))]
    .map((x) => x.toString(16).padStart(2, '0'))
    .join('');
  if (raw.byteLength > bytes || actual !== sha) throw new CityError('INVALID_DATA');
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)) as unknown;
}
let catalog: z.infer<typeof catalogDto> | null = null;
const cache = new Map<string, Street[]>();
const selections = new Map<string, Street[]>();
export async function loadStreets(center: [number, number], distance: number, signal: AbortSignal) {
  if (!catalog)
    catalog = catalogDto.parse(
      await read(
        '/data/seoul-streets-v1/catalog.json',
        '13d7a611ec46e0930a92951646edc2fd10a566627ad51ec164c9574a4f8dab9a',
        40000,
        signal
      )
    );
  const radius = Math.min(2600, Math.max(800, distance)) + 750;
  const references =
    distance > 9000
      ? [catalog.overview]
      : catalog.tiles.filter(
          (t) =>
            t.bounds[0] < center[0] + radius &&
            t.bounds[2] > center[0] - radius &&
            t.bounds[1] < center[1] + radius &&
            t.bounds[3] > center[1] - radius
        );
  const key = references
    .map((ref) => ref.sha256)
    .sort()
    .join(',');
  const selected = selections.get(key);
  if (selected) return selected;
  const roads = await Promise.all(
    references.map(async (ref) => {
      if (cache.has(ref.sha256)) return cache.get(ref.sha256)!;
      const value = streetsDto.parse(
        await read('/data/seoul-streets-v1/' + ref.file, ref.sha256, ref.bytes, signal)
      ).roads;
      if (!signal.aborted) {
        cache.set(ref.sha256, value);
        while (cache.size > 25) cache.delete(cache.keys().next().value!);
      }
      return value;
    })
  );
  const result = [...new Map(roads.flat().map((r) => [r.id, r])).values()];
  if (!signal.aborted) {
    selections.set(key, result);
    while (selections.size > 4) selections.delete(selections.keys().next().value!);
  }
  return result;
}
let population: Population | null = null;
export async function loadPopulation(signal: AbortSignal) {
  if (population) return population;
  const values = z.record(z.string(), z.array(z.number().nonnegative().max(5000000)).length(24));
  const schema = z.object({
    schemaVersion: z.literal(1),
    event2022: values,
    reference2025: values,
  });
  population = schema.parse(
    await read(
      '/data/city-population-v1.json',
      '206771f5394c2b425cdbe93e7b1dc6b242aa4e654a34cb38d0ada19ff0e4020f',
      150000,
      signal
    )
  );
  return population;
}
