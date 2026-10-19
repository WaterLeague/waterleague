import { readPublicData } from '../../../shared/repository/publicDataCache';
import { z } from 'zod';

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
const detailsDto = z
  .array(
    z.object({
      id: z.string().regex(/^way\/\d+:\d+$/),
      widthM: z.number().positive().max(80),
      footway: z.string().max(80),
      crossing: z.string().max(80),
      lanes: z
        .number()
        .int()
        .min(0)
        .max(12)
        .transform((n) => n || null),
      layer: z.number().int().min(0).max(20),
      bridge: z.boolean(),
      bridgeName: z.string().max(200),
      structure: z.string().max(80),
      sidewalkLeft: z.string().max(80),
      sidewalkRight: z.string().max(80),
      service: z.string().max(80),
      elevationsM: z.array(z.number().finite().min(-100).max(1500)).max(30000).optional(),
      junctionStartM: z.number().nonnegative().max(100),
      junctionEndM: z.number().nonnegative().max(100),
      walkPolygons: z.array(z.array(z.array(point).min(4))).optional(),
      structureSource: z.string().url().optional(),
    })
  )
  .max(30000);
const detailCatalogDto = z.object({
  schemaVersion: z.literal(1),
  streetCatalogSha256: z.literal(
    '13d7a611ec46e0930a92951646edc2fd10a566627ad51ec164c9574a4f8dab9a'
  ),
  entries: z.array(file).max(500),
});
let detailCatalog: z.infer<typeof detailCatalogDto> | null = null;
export const read = readPublicData;
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
  if (!detailCatalog)
    detailCatalog = detailCatalogDto.parse(
      await read(
        '/data/street-details-v1/catalog.json',
        'a549d7765fba6b28beda4cfa0fc5df53937b81b7fc13f1a9d0aca5bf0bac92bb',
        30000,
        signal
      )
    );
  const viewX = Math.round(center[0] / 200) * 200,
    viewY = Math.round(center[1] / 200) * 200;
  const viewRadius = Math.min(3100, Math.max(400, Math.round(distance / 400) * 400 * 1.1 + 300));
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
  const sourceKey = references
    .map((ref) => ref.sha256)
    .sort()
    .join(',');
  const key = sourceKey + (distance > 9000 ? '' : `:${viewX}:${viewY}:${viewRadius}`);
  const selected = selections.get(key);
  if (selected) return selected;
  const roads = await Promise.all(
    references.map(async (ref) => {
      if (cache.has(ref.sha256)) return cache.get(ref.sha256)!;
      const detailRef = detailCatalog!.entries.find((d) => d.file === ref.file)!;
      const [raw, rawDetails] = await Promise.all([
        read('/data/seoul-streets-v1/' + ref.file, ref.sha256, ref.bytes, signal),
        read(
          '/data/street-details-v1/' + detailRef.file,
          detailRef.sha256,
          detailRef.bytes,
          signal
        ),
      ]);
      const details = new Map(detailsDto.parse(rawDetails).map((d) => [d.id, d]));
      const value = streetsDto.parse(raw).roads.map((road) => {
        const detail = details.get(road.id);
        if (
          !detail ||
          (detail.elevationsM && detail.elevationsM.length !== road.coordinates.length)
        )
          throw new Error('도로 표시 자료 연결 오류');
        return { ...road, ...detail };
      });
      if (!signal.aborted) {
        cache.set(ref.sha256, value);
        while (cache.size > 25) cache.delete(cache.keys().next().value!);
      }
      return value;
    })
  );
  const all = [...new Map(roads.flat().map((r) => [r.id, r])).values()];
  const result =
    distance > 9000
      ? all
      : all.filter((road) => {
          let minX = Infinity,
            minY = Infinity,
            maxX = -Infinity,
            maxY = -Infinity;
          for (const [x, y] of road.coordinates) {
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
          }
          return (
            minX < viewX + viewRadius &&
            maxX > viewX - viewRadius &&
            minY < viewY + viewRadius &&
            maxY > viewY - viewRadius
          );
        });
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
