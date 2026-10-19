import type { z } from 'zod';
import type { installationDto, siteDto } from '../dto/installationDto';
export type SharedInstallation = z.infer<typeof installationDto>;
export type InstallationLayout = Pick<
  SharedInstallation,
  'id' | 'districtId' | 'cellId' | 'ownerId' | 'facilityType' | 'areaM2'
>;
export type SharedSite = z.infer<typeof siteDto>;
export const siteKey = (s: { districtId: string; cellId: string }) => `${s.districtId}:${s.cellId}`;
