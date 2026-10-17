import { useEffect, useState } from 'react';
export function GameClock() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const update = () => setNow(Date.now());
    const timer = window.setInterval(update, 1000);
    document.addEventListener('visibilitychange', update);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, []);
  return (
    <time
      className="game-live-clock"
      dateTime={new Date(now).toISOString()}
      aria-label="현재 한국 시각"
    >
      {new Date(now).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hourCycle: 'h23' })}
      <small>KST · 실시간</small>
    </time>
  );
}
