import { z } from 'zod';
const facility = z.enum(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']);
const point = z.tuple([z.number().finite(), z.number().finite()]);
export const installationDto = z.object({
  id: z.uuid(),
  districtId: z.string(),
  cellId: z.string(),
  ownerId: z.uuid(),
  ownerName: z.string().max(40),
  facilityType: facility,
  areaM2: z.number().positive(),
  cost: z.number().nonnegative(),
  installedAt: z.iso.datetime(),
});
export const siteDto = z.object({
  districtId: z.string(),
  cellId: z.string(),
  name: z.string(),
  kind: z.enum(['ROOF', 'GROUND']),
  coordinates: z.array(point).min(4),
  center: point,
  heightM: z.number().nonnegative(),
  maxAreaM2: z.number().positive(),
  allowedTypes: z.array(facility).min(1),
  unitCosts: z.record(facility, z.number().positive()),
  budget: z.number().positive(),
  modelHash: z.string().regex(/^[a-f0-9]{64}$/),
});
