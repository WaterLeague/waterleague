import { useEffect, useState, type RefObject } from 'react';
import { Maximize, Minimize } from 'lucide-react';
export function FullscreenButton({ target }: { target: RefObject<HTMLDivElement | null> }) {
  const [active, setActive] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const changed = () => setActive(document.fullscreenElement === target.current);
    document.addEventListener('fullscreenchange', changed);
    return () => document.removeEventListener('fullscreenchange', changed);
  }, [target]);
  return (
    <div className="fullscreen-control">
      <button
        aria-label={active ? '전체화면 종료' : '게임 전체화면'}
        title={active ? '전체화면 종료 · Esc' : '게임 전체화면'}
        onClick={async () => {
          setError('');
          try {
            if (active) await document.exitFullscreen();
            else if (target.current?.requestFullscreen) await target.current.requestFullscreen();
            else setError('이 브라우저에서는 전체화면을 지원하지 않습니다.');
          } catch {
            setError('전체화면을 열지 못했습니다. 브라우저의 전체화면 권한을 확인해 주세요.');
          }
        }}
      >
        {active ? <Minimize size={18} /> : <Maximize size={18} />}
      </button>
      {error && <span role="status">{error}</span>}
    </div>
  );
}
