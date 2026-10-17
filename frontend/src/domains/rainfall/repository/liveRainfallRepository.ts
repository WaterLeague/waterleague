import { api } from '../../../shared/repository/apiClient';
import { liveRainfallDto } from '../dto/liveRainfallDto';
import { ApiError } from '../../../shared/exception/ApiError';
export async function loadLiveRainfall() {
  const parsed = liveRainfallDto.safeParse(await api<unknown>('/rainfall/live'));
  if (!parsed.success)
    throw new ApiError(502, 'RAINFALL_DATA_INVALID', '실시간 강우 응답을 확인하지 못했습니다.');
  return parsed.data;
}
