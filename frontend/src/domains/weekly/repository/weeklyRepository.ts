import { api } from '../../../shared/repository/apiClient';
import { weeklyDto } from '../dto/weeklyDto';
export async function loadWeekly() {
  return weeklyDto.parse(await api('/weekly'));
}
