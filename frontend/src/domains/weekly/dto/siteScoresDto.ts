import { z } from 'zod';
import { installationDto } from '../../installation/dto/installationDto';
export const siteScoresDto = z.object({
  installations: z
    .array(
      installationDto
        .pick({
          id: true,
          ownerId: true,
          ownerName: true,
          facilityType: true,
          areaM2: true,
          installedAt: true,
          seasonEndsAt: true,
        })
        .extend({
          scoreM3: z.number().finite().nullable(),
          evaluatedMinutes: z.number().int().nonnegative(),
          evaluatedThrough: z.iso.datetime().nullable(),
        })
    )
    .max(50),
  nextAfterId: z.uuid().nullable(),
});
export type SiteScoresPage = z.infer<typeof siteScoresDto>;
