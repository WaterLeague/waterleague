import { siteScoresDto } from '../dto/siteScoresDto';
import { api } from '../../../shared/repository/apiClient';
import { weeklyDto } from '../dto/weeklyDto';
export async function loadWeekly() {
  return weeklyDto.parse(await api('/weekly'));
}

export async function loadSiteScores(
  district: string,
  cell: string,
  after: string | null,
  signal: AbortSignal
) {
  return siteScoresDto.parse(
    await api(
      `/weekly/sites/${encodeURIComponent(district)}/${encodeURIComponent(cell)}${after ? '?after=' + encodeURIComponent(after) : ''}`,
      'GET',
      undefined,
      signal
    )
  );
}
