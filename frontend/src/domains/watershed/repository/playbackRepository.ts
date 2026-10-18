import { api } from '../../../shared/repository/apiClient';
import { playbackCatalogDto, playbackFrameDto } from '../dto/playbackDto';
export const loadPlaybackCatalog = async (jobId: string, signal: AbortSignal) =>
  playbackCatalogDto.parse(
    await api(`/watersheds/${encodeURIComponent(jobId)}/playback`, 'GET', undefined, signal)
  );
export const loadPlaybackFrame = async (jobId: string, seconds: number, signal: AbortSignal) =>
  playbackFrameDto.parse(
    await api(
      `/watersheds/${encodeURIComponent(jobId)}/playback/frame?seconds=${seconds}`,
      'GET',
      undefined,
      signal
    )
  );
