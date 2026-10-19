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
          rainState: z.enum(['WET', 'SNOW', 'NO_RAIN_DETECTED', 'UNKNOWN']),
          rainObservedAt: z.iso.datetime().nullable(),
          rainEvidence: z.enum([
            'AWS_RAIN_SENSOR',
            'AWS_MINUTE_INCREMENT',
            'AWS_PRESENT_WEATHER',
            'UNKNOWN',
          ]),
          presentWeatherCode: z.number().int().min(0).max(99).nullable(),
          temperatureC: z.number().finite().min(-90).max(60).nullable(),
          humidityPercent: z.number().finite().min(0).max(100).nullable(),
          windSpeedMs: z.number().finite().min(0).max(150).nullable(),
          windDirectionDeg: z.number().finite().min(0).max(360).nullish(),
          pressureHpa: z.number().finite().min(300).max(1100).nullable(),
        })
      )
      .length(25),
  })
  .refine((v) => new Set(v.districts.map((d) => d.districtId)).size === 25);
