import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { installationDto, siteDto, sitePageDto } from '../dto/installationDto';
import type { FacilityType } from '../../game/entity/game';
export const loadInstallations = async () =>
  z.array(installationDto).parse(await api<unknown>('/installations'));
export type SiteQuery = {
  districtId: string;
  x: number;
  y: number;
  offset: number;
  type: FacilityType | '';
  vacant: boolean;
};
export const loadSites = async (query: SiteQuery, signal?: AbortSignal) => {
  const params = new URLSearchParams({
    districtId: query.districtId,
    x: String(query.x),
    y: String(query.y),
    offset: String(query.offset),
    vacant: String(query.vacant),
  });
  if (query.type) params.set('type', query.type);
  return sitePageDto.parse(
    await api<unknown>('/installations/sites?' + params, 'GET', undefined, signal)
  );
};
export const loadSite = async (districtId: string, cellId: string) =>
  siteDto.parse(
    await api<unknown>(
      '/installations/sites/' + encodeURIComponent(districtId) + '/' + encodeURIComponent(cellId)
    )
  );

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

export const loadBuildingSite = async (districtId: string, sourceId: string) =>
  siteDto.parse(
    await api<unknown>(
      '/installations/sites/' +
        encodeURIComponent(districtId) +
        '/building?sourceId=' +
        encodeURIComponent(sourceId)
    )
  );
