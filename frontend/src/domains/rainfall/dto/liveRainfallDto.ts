import { z } from 'zod';
const depth = z.number().finite().nonnegative().max(5000).nullable();
export const liveRainfallDto = z
  .object({
    fetchedAt: z.iso.datetime(),
    requestedObservationAt: z.iso.datetime(),
    source: z.literal('KMA_AWS_DIRECT'),
    sourceUrl: z.literal('https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239'),
    districts: z
      .array(
        z.object({
          districtId: z.string(),
          districtName: z.string(),
          stationId: z.string(),
          stationName: z.string(),
          observedAt: z.iso.datetime().nullable(),
          ageSeconds: z.number().int().nonnegative().nullable(),
          status: z.enum(['CURRENT', 'DELAYED', 'MISSING']),
          fifteenMinuteMm: depth,
          sixtyMinuteMm: depth,
          dayMm: depth,
          rainDetected: z.boolean().nullable(),
          oneMinuteMm: depth,
          rainState: z.enum(['WET', 'NO_RAIN_DETECTED', 'UNKNOWN']),
        })
      )
      .length(25),
  })
  .refine((v) => new Set(v.districts.map((d) => d.districtId)).size === 25);
