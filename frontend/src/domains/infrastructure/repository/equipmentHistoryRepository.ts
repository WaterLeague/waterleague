import { api } from '../../../shared/repository/apiClient';
import { equipmentHistoryDto, type EquipmentHistoryCatalog } from '../dto/equipmentHistoryDto';

const cache = new Map<string, Promise<EquipmentHistoryCatalog>>();
export function loadEquipmentHistory(eventId: string) {
  if (!['', 'seoul-20100921', 'seoul-20110727', 'seoul-20220808'].includes(eventId)) {
    return Promise.reject(new Error('지원하지 않는 재해 이력'));
  }
  let pending = cache.get(eventId);
  if (!pending) {
    const query = eventId ? `?eventId=${encodeURIComponent(eventId)}` : '';
    pending = api<unknown>(`/infrastructure/equipment-history-20261018-v1${query}`)
      .then((raw) => {
        const result = equipmentHistoryDto.parse(raw);
        if (result.eventId !== (eventId || null)) throw new Error('재해 이력 불일치');
        return result;
      })
      .catch((error) => {
        cache.delete(eventId);
        throw error;
      });
    cache.set(eventId, pending);
  }
  return pending;
}
