import { z } from 'zod';

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const coordinate = z.number().finite().min(-60000).max(60000);
export const traceTileIndexDto = z.object({
  id: z.string().regex(/^-?\d+_-?\d+$/),
  bounds: z.tuple([coordinate, coordinate, coordinate, coordinate]),
  sha256: hash,
  bytes: z.number().int().positive().max(10_000_000),
});
export const traceEventDto = z.object({
  id: z.enum(['seoul-20100921', 'seoul-20110727', 'seoul-20220808']),
  title: z.string().max(100),
  year: z.number().int(),
  periodStart: z.iso.date(),
  periodEnd: z.iso.date(),
  fileModifiedAt: z.iso.date(),
  sourceSha256: hash,
  recordCount: z.number().int().nonnegative(),
  includedCount: z.number().int().nonnegative(),
  statusCounts: z.record(z.string(), z.number().int().nonnegative()),
  unionAreaM2: z.number().finite().nonnegative(),
  tiles: z.array(traceTileIndexDto).max(200),
});
export const traceCatalogDto = z.object({
  sha256: z.literal('fb66992c100684d2e79c249962f1a05e0b967f2b2baa25bc8a7d91b4695ea4f4'),
  catalog: z.object({
    version: z.literal('seoul-flood-traces-20261018-v1'),
    usage: z.literal('OBSERVED_EVENT_EXTENT_REFERENCE'),
    projection: z.literal('EPSG:5186'),
    originM: z.tuple([z.literal(198128), z.literal(551989)]),
    displayRoundingM: z.literal(0.001),
    tileSizeM: z.literal(4000),
    sourceUrl: z.literal('https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do'),
    publisher: z.literal('서울특별시'),
    license: z.literal('KOGL_TYPE_1'),
    events: z.array(traceEventDto).length(3),
  }),
});
export const traceTileDto = z.object({
  eventId: traceEventDto.shape.id,
  id: traceTileIndexDto.shape.id,
  path: z
    .string()
    .max(3_000_000)
    .regex(/^[MLZ0-9.,e+\- ]+$/),
  triangleVertices: z
    .array(coordinate)
    .min(6)
    .max(1_000_000)
    .refine((v) => v.length % 6 === 0),
});
