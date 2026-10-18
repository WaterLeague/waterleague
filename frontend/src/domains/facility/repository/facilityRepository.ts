import { api } from '../../../shared/repository/apiClient';
import { facilityCatalogDto, type FacilityCatalog } from '../dto/facilityDto';
const pending = new Map<string, Promise<FacilityCatalog>>();
export function loadFacilityCatalog(id = 'EPA_LID_PUBLIC_DESIGNS_V4') {
  const version =
    id === 'EPA_LID_PUBLIC_DESIGNS_V1'
      ? 'v1'
      : id === 'EPA_LID_PUBLIC_DESIGNS_V2'
        ? 'v2'
        : id === 'EPA_LID_PUBLIC_DESIGNS_V3'
          ? 'v3'
          : 'v4';
  let request = pending.get(version);
  if (!request) {
    request = api<unknown>(`/facilities/epa-designs-${version}`)
      .then((v) => facilityCatalogDto.parse(v))
      .catch((error) => {
        pending.delete(version);
        throw error;
      });
    pending.set(version, request);
  }
  return request;
}
