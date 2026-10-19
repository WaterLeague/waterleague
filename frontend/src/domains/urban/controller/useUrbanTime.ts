import { useEffect, useRef } from 'react';
import type { UrbanTime } from '../entity/urban';
export function useUrbanTime(
  historical: boolean,
  at: string | null,
  playing: boolean,
  speed: number
): UrbanTime {
  const clock = useRef({
    historical,
    at: at ? Date.parse(at) : null,
    playing,
    speed,
    sampledAt: performance.now(),
    listeners: new Set<() => void>(),
  });
  useEffect(() => {
    clock.current = {
      historical,
      at: at ? Date.parse(at) : null,
      playing,
      speed,
      sampledAt: performance.now(),
      listeners: clock.current.listeners,
    };
    clock.current.listeners.forEach((listener) => listener());
  }, [historical, at, playing, speed]);
  return clock;
}
