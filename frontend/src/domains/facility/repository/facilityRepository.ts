import { api } from '../../../shared/repository/apiClient';
import { facilityCatalogDto, type FacilityCatalog } from '../dto/facilityDto';
let pending: Promise<FacilityCatalog> | null = null;
export function loadFacilityCatalog() {
  pending ??= api<unknown>('/facilities/epa-designs-v1')
    .then((v) => facilityCatalogDto.parse(v))
    .catch((error) => {
      pending = null;
      throw error;
    });
  return pending;
}
