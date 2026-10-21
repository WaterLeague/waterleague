import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { weeklyDto } from '../../weekly/dto/weeklyDto';
import { installationDto } from '../../competition/dto/competitionDto';
const result = z.object({
  period: weeklyDto.shape.current,
  installations: z.array(installationDto),
  page: z.number().int(),
  hasMore: z.boolean(),
});
export type SeasonResults = z.infer<typeof result>;
export const loadSeasons = async (signal?: AbortSignal) =>
  z.array(z.iso.date()).parse(await api('/admin/results/seasons', 'GET', undefined, signal));
export const loadSeasonResults = async (week: string, page: number, signal?: AbortSignal) =>
  result.parse(
    await api(
      `/admin/results/weekly?week=${encodeURIComponent(week)}&page=${page}`,
      'GET',
      undefined,
      signal
    )
  );
