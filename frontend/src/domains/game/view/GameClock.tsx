import { useEffect, useState } from 'react';
export function GameClock({ at, label = 'KST · 실시간' }: { at?: string; label?: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (at) return;
    const update = () => setNow(Date.now());
    const timer = window.setInterval(update, 1000);
    document.addEventListener('visibilitychange', update);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, [at]);
  const instant = at ? new Date(at) : new Date(now);
  return (
    <time
      className="game-live-clock"
      dateTime={instant.toISOString()}
      aria-label={at ? '재해 재생 시각' : '현재 한국 시각'}
    >
      {instant.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hourCycle: 'h23' })}
      <small>{label}</small>
    </time>
  );
}
