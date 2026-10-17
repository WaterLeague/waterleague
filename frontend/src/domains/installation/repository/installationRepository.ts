import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { installationDto, siteDto } from '../dto/installationDto';
import type { FacilityType } from '../../game/entity/game';
export const loadInstallations = async () =>
  z.array(installationDto).parse(await api<unknown>('/installations'));
export const loadSites = async () =>
  z.array(siteDto).parse(await api<unknown>('/installations/sites'));
export const installSite = async (
  districtId: string,
  cellId: string,
  facilityType: FacilityType,
  areaM2: number
) =>
  installationDto.parse(
    await api<unknown>('/installations', 'POST', { districtId, cellId, facilityType, areaM2 })
  );
export const removeInstallation = (id: string) =>
  api<void>('/installations/' + encodeURIComponent(id), 'DELETE');
