import { useEffect, useRef, useState } from 'react';
import type { City } from '../../city/entity/city';
import type { PlanView } from '../../city/service/planNavigationService';
import type { PublicSurfaceCurrent } from '../dto/publicSurfaceDto';
import { loadPublicSurfaces, loadPublicSurfaceFrame } from '../repository/publicSurfaceRepository';
import {
  bindPublicFrame,
  currentPublicFrames,
  type PublicFrame,
} from '../service/publicSurfaceService';
import { liveSurfaceFrameIndex, surfaceBounds } from '../service/surfaceService';
import { errorMessage } from '../../../shared/exception/ApiError';

export function usePublicSurfaces(enabled: boolean, camera: PlanView, city: City) {
  const boundsKey = surfaceBounds(camera).join(',');
  const [revision, refresh] = useState(0);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [tick, setTick] = useState(() => performance.now());
  const [state, setState] = useState<{
    key: string;
    current: PublicSurfaceCurrent;
    receivedAt: number;
    frames: PublicFrame[];
  } | null>(null);
  const latestState = useRef(state);
  useEffect(() => {
    latestState.current = state;
  }, [state]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const handler = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);
  useEffect(() => {
    if (!enabled || !visible) return;
    const poll = window.setInterval(() => refresh((v) => v + 1), 60000);
    return () => clearInterval(poll);
  }, [enabled, visible]);
  useEffect(() => {
    if (!enabled || !visible || !state) return;
    const now = Date.parse(state.current.serverNow) + performance.now() - state.receivedAt;
    const deadlines = state.current.runs
      .map((run) => Date.parse(run.lastFrameAt) + 300001)
      .filter((at) => at > now);
    if (!deadlines.length) return;
    // 물리 프레임의 유효 시각에만 갱신하여 빈 지도에 매초 렌더링을 발생시키지 않는다.
    const timer = window.setTimeout(() => setTick(performance.now()), Math.min(...deadlines) - now);
    return () => clearTimeout(timer);
  }, [enabled, visible, state, tick]);
  useEffect(() => {
    if (!enabled || !visible) return;
    const controller = new AbortController();
    const bounds = boundsKey.split(',').map(Number);
    setLoading(true);
    setError('');
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const receivedAt = performance.now();
          const current = await loadPublicSurfaces(bounds, controller.signal);
          if (controller.signal.aborted) return;
          setTick(performance.now());
          if (
            current.runs.some((run) =>
              run.catalog.originProjected.some((v, i) => v !== city.originProjected[i])
            )
          )
            throw new Error('공개 계산의 지도 좌표 기준이 다릅니다.');
          const now = Date.parse(current.serverNow);
          const previous = latestState.current;
          const retained = currentPublicFrames(
            current,
            previous?.key === boundsKey ? previous.frames : [],
            now + performance.now() - receivedAt
          );
          setState({ key: boundsKey, current, receivedAt, frames: retained });
          // 유역별 원 프레임을 유지하며 겹치는 회원 설계나 물량을 하나로 합산하지 않는다.
          const available = new Set(retained.map((value) => value.id));
          const pending = current.runs.filter((run) => !available.has(run.id));
          await Promise.all(
            Array.from({ length: Math.min(4, pending.length) }, async () => {
              while (pending.length && !controller.signal.aborted) {
                const run = pending.shift()!;
                const index = liveSurfaceFrameIndex(
                  run.catalog,
                  now + performance.now() - receivedAt
                );
                if (index === null) continue;
                try {
                  const raw = await loadPublicSurfaceFrame(
                    run.id,
                    index,
                    bounds,
                    controller.signal
                  );
                  if (controller.signal.aborted) return;
                  const value = bindPublicFrame(run, raw, now + performance.now() - receivedAt);
                  setTick(performance.now());
                  setState((previous) =>
                    previous?.current === current
                      ? { ...previous, frames: [...previous.frames, value] }
                      : previous
                  );
                } catch (e) {
                  if (!controller.signal.aborted) setError(errorMessage(e));
                }
              }
            })
          );
        } catch (e) {
          if (!controller.signal.aborted) {
            setState(null);
            setError(errorMessage(e));
          }
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      })();
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, visible, boundsKey, revision, city.originProjected]);
  const current = enabled && visible && state?.key === boundsKey ? state.current : null;
  const now = state
    ? Date.parse(state.current.serverNow) + Math.max(0, performance.now() - state.receivedAt)
    : NaN;
  const frames = currentPublicFrames(current, state?.frames ?? [], now);
  return {
    current,
    frames,
    loading: enabled && loading,
    error: enabled ? error : '',
    retry: () => refresh((v) => v + 1),
  };
}
