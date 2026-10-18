import { useEffect, useState } from 'react';
import type { PlaybackCatalog, PlaybackFrame } from '../dto/playbackDto';
import { loadPlaybackCatalog, loadPlaybackFrame } from '../repository/playbackRepository';
import { requirePlaybackBinding } from '../service/playback';
import { ApiError } from '../../../shared/exception/ApiError';
export function useWatershedPlayback(jobId: string) {
  const [catalog, setCatalog] = useState<PlaybackCatalog | null>(null);
  const [frame, setFrame] = useState<PlaybackFrame | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setCatalog(null);
    setFrame(null);
    setIndex(0);
    setPlaying(false);
    setError('');
    void loadPlaybackCatalog(jobId, AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]))
      .then((v) => {
        if (!abort.signal.aborted) {
          if (v.jobId !== jobId) throw new Error();
          setCatalog(v);
        }
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setError(e instanceof ApiError ? e.message : '관망 재생 자료를 확인하지 못했습니다.');
      });
    return () => abort.abort();
  }, [jobId, revision]);
  useEffect(() => {
    if (!catalog || catalog.jobId !== jobId) return;
    const abort = new AbortController();
    setFrame(null);
    setError('');
    // 슬라이더 이동 중 요청을 합치고 다른 시각의 응답이 현재 화면을 덮지 않게 한다.
    const timer = setTimeout(() => {
      void loadPlaybackFrame(
        jobId,
        catalog.timesSeconds[index],
        AbortSignal.any([abort.signal, AbortSignal.timeout(15000)])
      )
        .then((v) => {
          if (!abort.signal.aborted)
            setFrame(requirePlaybackBinding(catalog, v, catalog.timesSeconds[index]));
        })
        .catch((e: unknown) => {
          if (!abort.signal.aborted) {
            setPlaying(false);
            setError(
              e instanceof ApiError ? e.message : '이 시각의 원 계산 기록을 확인하지 못했습니다.'
            );
          }
        });
    }, 100);
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [jobId, catalog, index]);
  useEffect(() => {
    if (!playing || !catalog || !frame || error) return;
    if (index >= catalog.timesSeconds.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = setTimeout(() => {
      if (!document.hidden) setIndex((i) => i + 1);
      else setPlaying(false);
    }, 750);
    return () => clearTimeout(timer);
  }, [playing, catalog, frame, index, error]);
  return {
    catalog,
    frame:
      frame?.jobId === jobId && frame.requestedTimeSeconds === catalog?.timesSeconds[index]
        ? frame
        : null,
    index,
    playing,
    error,
    setIndex,
    setPlaying,
    retry: () => setRevision((v) => v + 1),
  };
}
