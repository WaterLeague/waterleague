import { useEffect } from 'react';

export function useGameInteractions() {
  useEffect(() => {
    // 지도·슬라이더의 포인터 조작은 유지하고 브라우저 기본 동작만 차단한다.
    const preventDefault = (event: Event) => event.preventDefault();
    document.addEventListener('contextmenu', preventDefault, true);
    document.addEventListener('dragstart', preventDefault, true);
    return () => {
      document.removeEventListener('contextmenu', preventDefault, true);
      document.removeEventListener('dragstart', preventDefault, true);
    };
  }, []);
}
