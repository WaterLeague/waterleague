import { api } from '../../../shared/repository/apiClient';
import { mapSpatial } from '../mapper/spatialMapper';
export async function loadSpatial() {
  return mapSpatial(await api<unknown>('/spatial/buildings'));
}
