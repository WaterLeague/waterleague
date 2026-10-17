import { useCallback, useEffect, useRef, useState } from 'react';
import type { StormReplayData } from '../entity/stormReplay';
import { replayIndexAtTime } from '../service/stormReplayService';

export function useStormReplay(data: StormReplayData) {
  const [index, setIndex] = useState(data.firstWetIndex);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(60);
  const current = useRef(index);
  current.current = index;
  const count = data.frames.length;
  const seek = useCallback(
    (next: number) => {
      setPlaying(false);
      setIndex(Math.max(0, Math.min(count - 1, Math.round(next))));
    },
    [count]
  );
  useEffect(() => {
    if (!playing) return;
    const started = performance.now(),
      initial = current.current;
    const timer = window.setInterval(() => {
      const next = replayIndexAtTime(initial, performance.now() - started, speed, count);
      setIndex(next);
      if (next === count - 1) setPlaying(false);
    }, 100);
    const hide = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener('visibilitychange', hide);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', hide);
    };
  }, [playing, speed, count]);
  function toggle() {
    if (!playing && index === count - 1) {
      current.current = 0;
      setIndex(0);
    }
    setPlaying((v) => !v);
  }
  return { index, playing, speed, setSpeed, seek, toggle };
}
