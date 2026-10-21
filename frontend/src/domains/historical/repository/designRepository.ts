import { competitionScope } from '../../competition/repository/competitionScope';
import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { siteDto } from '../../installation/dto/installationDto';
import type { HistoricalDraft } from '../entity/historical';
const itemDto = z.object({
  id: z.uuid(),
  districtId: z.string(),
  cellId: z.string(),
  facilityType: z.enum([
    'RAIN_GARDEN',
    'PERMEABLE_PAVEMENT',
    'GREEN_ROOF',
    'BIORETENTION',
    'VEGETATIVE_SWALE',
    'INFILTRATION_TRENCH',
    'RAINWATER_CISTERN',
  ]),
  areaM2: z.number().positive(),
  installedAt: z.iso.datetime(),
});
export const historicalDesignDto = z
  .object({
    eventId: z.string().regex(/^seoul-[0-9]{8}$/),
    revision: z.number().int().nonnegative(),
    snapshotSha256: z
      .string()
      .regex(/^[a-f0-9]{64}$/)
      .nullable(),
    createdAt: z.iso.datetime().nullable(),
    snapshot: z
      .object({
        schemaVersion: z.literal(1),
        eventId: z.string(),
        elapsedSeconds: z.number().int().nonnegative(),
        placements: z
          .array(
            z.object({
              item: itemDto,
              site: siteDto,
              cost: z.number().nonnegative(),
              rainfallModelHash: z.string().regex(/^[a-f0-9]{64}$/),
            })
          )
          .max(50),
      })
      .nullable(),
  })
  .refine((v) =>
    v.revision === 0
      ? v.snapshot === null && v.snapshotSha256 === null
      : !!v.snapshot && !!v.snapshotSha256 && v.snapshot.eventId === v.eventId
  );
export type HistoricalDesign = z.infer<typeof historicalDesignDto>;
export const designItems = (drafts: HistoricalDraft[]) =>
  drafts.map((d) => ({
    id: d.marker.id,
    districtId: d.site.districtId,
    cellId: d.site.cellId,
    facilityType: d.facilityType,
    areaM2: d.areaM2,
    installedAt: d.marker.installedAt,
  }));
export type DesignRequest = {
  requestKey: string;
  baseRevision: number;
  elapsedSeconds: number;
  placements: ReturnType<typeof designItems>;
};
function path(eventId: string) {
  if (!/^seoul-[0-9]{8}$/.test(eventId)) throw new Error('재해 사건을 확인해 주세요.');
  return '/historical/designs/' + eventId;
}
export const loadDesign = async (eventId: string, competitionId?: string | null) =>
  historicalDesignDto.parse(await api(competitionScope(path(eventId), competitionId)));
export const saveDesign = async (
  eventId: string,
  request: DesignRequest,
  competitionId?: string | null
) =>
  historicalDesignDto.parse(
    await api(competitionScope(path(eventId), competitionId), 'PUT', request)
  );
export function restoreDesign(value: HistoricalDesign, ownerId: string): HistoricalDraft[] {
  return (
    value.snapshot?.placements.map(({ item, site, cost }) => {
      if (
        item.districtId !== site.districtId ||
        item.cellId !== site.cellId ||
        !site.allowedTypes.includes(item.facilityType)
      )
        throw new Error('저장된 시설과 위치가 일치하지 않습니다.');
      return {
        site,
        facilityType: item.facilityType,
        areaM2: item.areaM2,
        marker: {
          id: item.id,
          ownerId,
          ownerName: '내 연구 설계',
          districtId: site.districtId,
          cellId: site.cellId,
          facilityType: item.facilityType,
          areaM2: item.areaM2,
          cost,
          installedAt: item.installedAt,
          center: site.center,
          heightM: site.heightM,
        },
      };
    }) ?? []
  );
}
