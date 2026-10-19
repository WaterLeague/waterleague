import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { PlanView } from '../../city/service/planNavigationService';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import type { UrbanTime } from '../../urban/entity/urban';
import type { FloodField } from '../../urban/service/floodFieldService';
import type { SharedSite } from '../../installation/entity/installation';
import { GameAudioEngine } from '../service/gameAudioEngine';

const preference = 'waterleague.sound.enabled';
function savedPreference() {
  try {
    return localStorage.getItem(preference) !== 'false';
  } catch {
    return true;
  }
}

export function useGameAudio(settings: {
  camera: RefObject<PlanView>;
  clock: UrbanTime;
  terrain: Terrain | null;
  flood: FloodField;
  rain: number;
  flat: boolean;
}) {
  const [enabled, setEnabled] = useState(savedPreference);
  const [unavailable, setUnavailable] = useState(false);
  const engine = useRef<GameAudioEngine | null>(null);
  const context = useRef<AudioContext | null>(null);
  const current = useRef(settings);
  const enabledRef = useRef(enabled);
  useEffect(() => {
    current.current = settings;
  });

  const activate = useCallback(() => {
    if (!enabledRef.current || document.hidden) return;
    try {
      if (!context.current) {
        const next = new AudioContext({ latencyHint: 'interactive' });
        context.current = next;
        void GameAudioEngine.create(next)
          .then((audio) => {
            if (context.current !== next || next.state === 'closed') {
              audio.dispose();
              return;
            }
            engine.current = audio;
            audio.mute(!enabledRef.current || document.hidden);
          })
          .catch(() => {
            if (context.current === next) {
              setUnavailable(true);
              void next.close().catch(() => {});
            }
          });
      }
      engine.current?.mute(false);
      if (context.current.state !== 'running') void context.current.resume().catch(() => {});
    } catch {
      setUnavailable(true);
    }
  }, []);

  useEffect(() => {
    let suspension: ReturnType<typeof setTimeout> | undefined;
    const visibility = () => {
      clearTimeout(suspension);
      if (document.hidden) {
        engine.current?.mute(true);
        suspension = setTimeout(() => {
          void context.current?.suspend().catch(() => {});
        }, 200);
      } else if (enabledRef.current) activate();
    };
    const gesture = () => {
      clearTimeout(suspension);
      activate();
    };
    document.addEventListener('pointerup', gesture);
    document.addEventListener('keydown', gesture);
    document.addEventListener('visibilitychange', visibility);
    if (navigator.userActivation?.hasBeenActive) activate();
    const update = () => {
      const audio = engine.current;
      if (!audio?.active || document.hidden || context.current?.state !== 'running') return;
      const { camera, clock, terrain, flood, rain, flat } = current.current;
      const view = camera.current;
      const height = terrainHeight(terrain, view.center);
      if (flat)
        audio.listener(
          [view.center[0], height + view.distance, -view.center[1]],
          [0, -1, 0],
          [0, 0, -1]
        );
      const wet = view.distance < 1800 ? flood.nearest(view.center, 500) : null;
      audio.environment({
        playing: !clock.current.historical || (clock.current.at !== null && clock.current.playing),
        speed: clock.current.historical ? clock.current.speed : 1,
        rain,
        distance: view.distance,
        flood: wet
          ? {
              point: [
                wet.point[0],
                terrainHeight(terrain, wet.point) + (wet.contact.depth ?? 0),
                -wet.point[1],
              ],
              depth: wet.contact.depth,
              speed: wet.contact.speed,
            }
          : null,
      });
    };
    const clockListeners = current.current.clock.current.listeners;
    clockListeners?.add(update);
    const timer = setInterval(update, 200);
    return () => {
      clearInterval(timer);
      clockListeners?.delete(update);
      clearTimeout(suspension);
      document.removeEventListener('pointerup', gesture);
      document.removeEventListener('keydown', gesture);
      document.removeEventListener('visibilitychange', visibility);
      engine.current?.dispose();
      engine.current = null;
      void context.current?.close().catch(() => {});
      context.current = null;
    };
  }, [activate]);

  useEffect(() => {
    if (enabled) return;
    const timer = setTimeout(() => {
      void context.current?.suspend().catch(() => {});
    }, 250);
    return () => clearTimeout(timer);
  }, [enabled]);

  const toggle = () => {
    const next = !enabledRef.current;
    enabledRef.current = next;
    setEnabled(next);
    try {
      localStorage.setItem(preference, String(next));
    } catch {
      /* 저장 불가 시 현재 화면 설정 유지 */
    }
    engine.current?.mute(!next);
    if (next) activate();
  };
  const installed = useCallback((site: Pick<SharedSite, 'center' | 'heightM'>) => {
    if (!enabledRef.current || document.hidden || context.current?.state !== 'running') return;
    engine.current?.installed([
      site.center[0],
      terrainHeight(current.current.terrain, site.center) + site.heightM,
      -site.center[1],
    ]);
  }, []);
  return { engine, enabled, unavailable, toggle, installed };
}
