import { api } from '../../../shared/repository/apiClient';
import { costRecordDto } from '../dto/costDto';

export const loadCostRecord = async (id: string, signal?: AbortSignal) =>
  costRecordDto.parse(
    await api<unknown>(
      '/installations/' + encodeURIComponent(id) + '/cost',
      'GET',
      undefined,
      signal
    )
  );
