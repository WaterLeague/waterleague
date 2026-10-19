import { z } from 'zod';
export const archivedWeatherDto = z.object({
  version: z.literal('ARCHIVED_WATER_WEATHER_V1'),
  entries: z
    .array(
      z.object({
        eventId: z.string(),
        stationName: z.string(),
        stationId: z.string(),
        resolution: z.enum(['HOUR', 'DAY']),
        sourceFile: z.string(),
        sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
        samples: z
          .array(
            z.object({
              from: z.iso.datetime({ offset: true }),
              until: z.iso.datetime({ offset: true }),
              windSpeedMs: z.number().finite().min(0).max(150),
            })
          )
          .max(48),
      })
    )
    .max(20),
});
export type ArchivedWeather = z.infer<typeof archivedWeatherDto>;
