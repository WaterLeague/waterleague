import { z } from 'zod';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const point = z.tuple([
  z.number().finite().min(-100000).max(100000),
  z.number().finite().min(-100000).max(100000),
]);
export const nativeTransportDto = z.object({
  schemaVersion: z.literal(1),
  lanes: z
    .array(
      z.tuple([
        z.string().regex(/^ngii:N1L_A0020000:[a-f0-9]{64}$/),
        z.number().int().min(2).max(32),
      ])
    )
    .max(150000),
  routes: z
    .array(
      z.object({
        id: sha,
        kind: z.enum(['rail', 'subway']),
        name: z.string().max(200),
        coordinates: z.array(point).min(2).max(100000),
        sourceFids: z.array(z.number().int().positive()).min(1).max(10000),
      })
    )
    .max(10000),
});
export type NativeTransport = z.infer<typeof nativeTransportDto>;
export const nativeTransportIndexDto = z.object({
  schemaVersion: z.literal(1),
  id: z.literal('SEOUL_NGII_TRANSPORT_V1'),
  file: z.literal('transport.json.gz'),
  sha256: sha,
  bytes: z.number().int().positive().max(20000000),
  sourceCitySha256: sha,
  sourceSpatialSha256: sha,
  counts: z.object({
    lanes: z.number().int().nonnegative(),
    routes: z.number().int().nonnegative(),
  }),
  policy: z.object({
    displayOnly: z.literal(true),
    observedPositions: z.literal(false),
    observedTimetable: z.literal(false),
    hydraulicInputsChanged: z.literal(false),
  }),
});
