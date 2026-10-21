import { useEffect, useRef, useState } from 'react';
import { useServerConnected } from '../../../shared/controller/serverConnectionContext';
import {
  previewElapsed,
  previewTime,
  previewTimeLabel,
  type PreviewTimeline,
} from '../service/homePreviewService';

export function usePreviewPlayback(mode: 'weekly' | 'disaster' | undefined, visible: boolean) {
  const connected = useServerConnected();
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [tabVisible, setTabVisible] = useState(true);
  const timeline = useRef<PreviewTimeline>({ epoch: Date.now(), elapsed: 0, startedAt: null });
  const [time, setTime] = useState(() => previewTimeLabel(timeline.current.epoch));
  const running = !!mode && visible && tabVisible && connected && !paused && !reduced;

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const preference = () => setReduced(media.matches);
    const visibility = () => setTabVisible(!document.hidden);
    preference();
    visibility();
    media.addEventListener('change', preference);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      media.removeEventListener('change', preference);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, []);

  useEffect(() => {
    const clock = timeline.current;
    if (!running) {
      setTime(previewTimeLabel(previewTime(clock, clock.elapsed)));
      return;
    }
    if (clock.elapsed === 0) clock.epoch = Date.now();
    clock.startedAt = performance.now();
    const update = () =>
      setTime(previewTimeLabel(previewTime(clock, previewElapsed(clock, performance.now()))));
    update();
    const timer = mode === 'weekly' ? window.setInterval(update, 250) : undefined;
    return () => {
      clock.elapsed = previewElapsed(clock, performance.now());
      clock.startedAt = null;
      window.clearInterval(timer);
    };
  }, [running, mode]);

  return { timeline, time, running, paused, reduced, toggle: () => setPaused((value) => !value) };
}
