import { useEffect, useRef, useState } from 'react';

export function usePreviewVisibility() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (!('IntersectionObserver' in window)) {
      setVisible(true);
      return;
    }
    // 화면 밖의 소개 장면은 GPU 컨텍스트와 모형을 유지하지 않는다.
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, visible };
}
