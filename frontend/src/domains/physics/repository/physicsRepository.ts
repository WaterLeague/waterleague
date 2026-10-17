import { api } from '../../../shared/repository/apiClient';
import { physicsDto } from '../dto/physicsDto';
export async function loadPhysics(id: string) {
  return physicsDto.parse(await api('/installations/' + encodeURIComponent(id) + '/physics'));
}
