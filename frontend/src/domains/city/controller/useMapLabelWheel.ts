import { useEffect, type RefObject } from 'react';

export function useMapLabelWheel(layer: RefObject<HTMLDivElement | null>, flat: boolean) {
  useEffect(() => {
    const element = layer.current;
    if (!element || flat) return;
    const forward = (event: WheelEvent) => {
      const canvas = element.parentElement?.querySelector('canvas');
      if (!canvas) return;
      // 표식 클릭은 유지하고 휠만 같은 지도의 OrbitControls에 전달한다.
      event.preventDefault();
      event.stopPropagation();
      canvas.dispatchEvent(
        new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          deltaX: event.deltaX,
          deltaY: event.deltaY,
          deltaZ: event.deltaZ,
          deltaMode: event.deltaMode,
          clientX: event.clientX,
          clientY: event.clientY,
          screenX: event.screenX,
          screenY: event.screenY,
          ctrlKey: event.ctrlKey,
          shiftKey: event.shiftKey,
          altKey: event.altKey,
          metaKey: event.metaKey,
        })
      );
    };
    element.addEventListener('wheel', forward, { passive: false });
    return () => element.removeEventListener('wheel', forward);
  }, [layer, flat]);
}
