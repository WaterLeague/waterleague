import { useEffect, useState } from 'react';
import type { City } from '../../city/entity/city';
import type { PlanView } from '../../city/service/planNavigationService';
import type { SurfaceCatalog, SurfaceFrame, SurfaceSource } from '../entity/surface';
import { loadSurfaceCatalog, loadSurfaceFrame } from '../repository/surfaceRepository';
import {
  assertSurfaceBinding,
  surfaceBounds,
  surfaceFrameIndex,
  liveSurfaceFrameIndex,
} from '../service/surfaceService';
import { ApiError, errorMessage } from '../../../shared/exception/ApiError';

export function useSurfacePlayback(
  enabled: boolean,
  source: SurfaceSource | null,
  actor: string | null,
  at: string | null,
  camera: PlanView,
  city: City,
  manualIndex: number | null,
  liveNow: number | null = null
) {
  const key = `${actor}/${source?.kind}/${source?.id}`;
  const [catalogState, setCatalog] = useState<{ key: string; value: SurfaceCatalog } | null>(null);
  const [frameState, setFrame] = useState<{
    key: string;
    index: number;
    bounds: string;
    value: SurfaceFrame;
  } | null>(null);
  const [error, setError] = useState(''),
    [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);
  const [expiryNow, setExpiryNow] = useState(0);
  const currentLiveTime = liveNow === null ? null : Math.max(liveNow, expiryNow);
  const catalog = enabled && catalogState?.key === key ? catalogState.value : null;
  const index = catalog
    ? currentLiveTime !== null
      ? liveSurfaceFrameIndex(catalog, currentLiveTime)
      : (manualIndex ?? surfaceFrameIndex(catalog, at))
    : null;
  const refreshMinute = liveNow === null ? null : Math.floor(liveNow / 60000);
  useEffect(() => {
    if (currentLiveTime === null || !catalog || index === null) return;
    const expires = Date.parse(catalog.startUtc) + catalog.timesSeconds[index] * 1000 + 300001;
    const timer = window.setTimeout(
      () => setExpiryNow(Date.now()),
      Math.max(0, expires - Date.now())
    );
    return () => window.clearTimeout(timer);
  }, [currentLiveTime, catalog, index]);
  const boundsKey = surfaceBounds(camera).join(',');
  useEffect(() => {
    setCatalog(null);
    setFrame(null);
    setError('');
    if (!enabled || !visible || !source || !actor) return;
    const controller = new AbortController();
    void loadSurfaceCatalog(source, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        if (value.originProjected.some((v, i) => v !== city.originProjected[i]))
          throw new Error('현재 지도와 계산 좌표 기준이 다릅니다.');
        setCatalog({ key, value });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof ApiError && e.status === 404
              ? '이 실행에는 지표 수심·속력 결과가 없습니다.'
              : errorMessage(e)
          );
      });
    return () => controller.abort();
  }, [key, enabled, visible, revision, city.originProjected, refreshMinute]);
  useEffect(() => {
    setFrame(null);
    setLoading(false);
    if (!enabled || !source || !catalog || index === null) return;
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      void loadSurfaceFrame(source, index, boundsKey.split(',').map(Number), controller.signal)
        .then((value) => {
          if (controller.signal.aborted) return;
          setFrame({
            key,
            index,
            bounds: boundsKey,
            value: assertSurfaceBinding(catalog, value, index),
          });
          setError('');
        })
        .catch((e) => {
          if (!controller.signal.aborted)
            setError(
              e instanceof ApiError && e.status === 413
                ? '표시 격자가 많습니다. 지도를 더 확대해 주세요.'
                : errorMessage(e)
            );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, enabled, catalog, index, boundsKey, revision]);
  const frame =
    enabled &&
    frameState?.key === key &&
    frameState.index === index &&
    frameState.bounds === boundsKey &&
    frameState.value.catalogSha256 === catalog?.catalogSha256
      ? frameState.value
      : null;
  return { catalog, frame, index, loading, error, retry: () => setRevision((v) => v + 1) };
}
