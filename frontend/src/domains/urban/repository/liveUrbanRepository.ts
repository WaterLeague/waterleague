import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { CityError } from '../../city/exception/CityError';
import type { UrbanArea, LivePlace } from '../entity/liveUrban';
import { read } from './urbanRepository';
export const AREA_HASH = 'a7612f567007844dba44f1334784314748f6dd19819e3c320f9ea63df832ee40';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const coordinate = z.number().min(-60000).max(60000);
const point = z.tuple([coordinate, coordinate]);
const catalog = z.object({
  schemaVersion: z.literal(1),
  originProjected: z.tuple([z.literal(198128), z.literal(551989)]),
  coordinateSystem: z.literal('EPSG:5186'),
  areas: z
    .array(
      z.object({
        id: z.string().regex(/^POI\d{3}$/),
        name: z.string().min(1).max(100),
        areaKm2: z.number().positive().max(100),
        bounds: z.tuple([coordinate, coordinate, coordinate, coordinate]),
        polygons: z.array(z.array(z.array(point).min(4))).min(1),
      })
    )
    .length(121),
});
const provenance = z.object({
  retrievedAt: z.iso.datetime(),
  validUntil: z.iso.datetime(),
  sourceSha256: hash,
});
const responseDto = z.object({
  catalogSha256: z.literal(AREA_HASH),
  sourceUrl: z.literal('https://data.seoul.go.kr/SeoulRtd/'),
  places: z
    .array(
      z.object({
        id: z.string(),
        name: z.string(),
        population: provenance
          .extend({
            minimum: z.number().int().nonnegative().max(5000000),
            maximum: z.number().int().nonnegative().max(5000000),
            sourceHourKst: z.number().int().min(0).max(23),
            congestion: z.enum(['여유', '보통', '약간 붐빔', '붐빔']),
          })
          .nullable(),
        traffic: provenance
          .extend({ speedKmh: z.number().min(0).max(180), observedAt: z.iso.datetime() })
          .nullable(),
      })
    )
    .max(6),
});
let areas: UrbanArea[] | null = null;
export async function loadLiveAreas(signal: AbortSignal) {
  if (areas) return areas;
  const parsed = catalog.parse(
    await read('/data/city-live-areas-v1.json', AREA_HASH, 600000, signal)
  );
  if (new Set(parsed.areas.map((a) => a.id)).size !== 121) throw new CityError('INVALID_DATA');
  areas = parsed.areas;
  return areas;
}
export async function loadLivePlaces(
  selected: UrbanArea[],
  signal: AbortSignal
): Promise<LivePlace[]> {
  if (!selected.length) return [];
  const data = responseDto.parse(
    await api<unknown>(
      `/urban/live?places=${selected.map((a) => a.id).join(',')}`,
      'GET',
      undefined,
      signal
    )
  );
  if (
    data.places.length !== selected.length ||
    new Set(data.places.map((p) => p.id)).size !== selected.length
  )
    throw new CityError('INVALID_DATA');
  const now = Date.now();
  return data.places.map((place) => {
    const area = selected.find((a) => a.id === place.id && a.name === place.name);
    if (!area || (place.population && place.population.minimum > place.population.maximum))
      throw new CityError('INVALID_DATA');
    for (const reading of [place.population, place.traffic]) {
      if (!reading) continue;
      const retrieved = Date.parse(reading.retrievedAt),
        until = Date.parse(reading.validUntil);
      if (retrieved > now + 120000 || until < retrieved || until > retrieved + 300000)
        throw new CityError('INVALID_DATA');
    }
    if (
      place.traffic &&
      (Date.parse(place.traffic.observedAt) > now + 120000 ||
        Date.parse(place.traffic.validUntil) > Date.parse(place.traffic.observedAt) + 900000)
    )
      throw new CityError('INVALID_DATA');
    return { ...area, population: place.population, traffic: place.traffic };
  });
}
