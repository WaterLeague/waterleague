import { z } from 'zod';
const windSample = z.tuple([
  z.number().finite().min(0).max(150).nullable(),
  z.number().finite().min(0).lt(360).nullable(),
]);
export const archivedWeatherDto = z
  .object({
    version: z.literal('ARCHIVED_WATER_WEATHER_V2'),
    eventId: z.enum(['seoul-20220808', 'seoul-20110727', 'seoul-20100921']),
    start: z.iso.datetime({ offset: true }),
    end: z.iso.datetime({ offset: true }),
    intervalSeconds: z.literal(60),
    fields: z.tuple([z.literal('WS1'), z.literal('WD1')]),
    timePolicy: z.literal('COMPLETED_ONE_MINUTE_MEAN_HELD_OVER_NEXT_MINUTE'),
    selectionSha256: z.string().regex(/^[a-f0-9]{64}$/),
    stations: z
      .array(
        z.object({
          stationId: z.string().regex(/^\d{1,4}$/),
          stationName: z.string().max(100),
          districtIds: z.array(z.string().regex(/^\d+$/)).min(1).max(25),
          sourceFile: z.string().regex(/^kma-\d{1,4}-\d{12}-\d{12}\.txt$/),
          sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
          samples: z.array(windSample).min(1).max(1440),
        })
      )
      .min(1)
      .max(25),
  })
  .refine((value) => {
    const count = (Date.parse(value.end) - Date.parse(value.start)) / 60000;
    const districts = value.stations.flatMap((station) => station.districtIds);
    return (
      Number.isInteger(count) &&
      count > 0 &&
      new Set(districts).size === districts.length &&
      new Set(value.stations.map((station) => station.stationId)).size === value.stations.length &&
      value.stations.every(
        (station) =>
          station.samples.length === count &&
          station.samples.every(
            ([speed, direction]) => direction === null || (speed !== null && speed > 0)
          )
      )
    );
  });
export type ArchivedWeather = z.infer<typeof archivedWeatherDto>;
