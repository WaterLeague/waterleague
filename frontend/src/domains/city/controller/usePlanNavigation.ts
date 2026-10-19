import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from 'react';
import type { CityFocus } from '../entity/city';
import {
  initialPlanView,
  zoomPlanView,
  planBox,
  type PlanView,
} from '../service/planNavigationService';

export function usePlanNavigation(
  focus: CityFocus,
  bounds: number[],
  initialCamera: PlanView,
  onCamera: (view: PlanView) => void,
  onNavigate: (view: PlanView) => void
) {
  const svg = useRef<SVGSVGElement>(null);
  const [view, setView] = useState(initialCamera);
  const [aspect, setAspect] = useState(1);
  const aspectRef = useRef(1);
  const focusKey = useRef(focus.key);
  const current = useRef(view);
  const drag = useRef<{ id: number; x: number; y: number; scale: number; view: PlanView } | null>(
    null
  );
  const moved = useRef(false);
  const frame = useRef<number | null>(null);
  const reportTimer = useRef<number | null>(null);
  const [dragging, setDragging] = useState(false);
  useLayoutEffect(() => {
    const element = svg.current;
    if (!element) return;
    const resize = () => {
      aspectRef.current = element.clientWidth / Math.max(1, element.clientHeight);
      setAspect(aspectRef.current);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (focusKey.current === focus.key) return;
    focusKey.current = focus.key;
    current.current = initialPlanView(focus, bounds, aspectRef.current);
    onNavigate(current.current);
    setView(current.current);
    onCamera(current.current);
  }, [focus, bounds, onCamera, onNavigate]);
  function change(next: PlanView) {
    current.current = next;
    onNavigate(next);
    if (frame.current === null)
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        const box = planBox(current.current, aspectRef.current);
        svg.current?.setAttribute('viewBox', `${box.x} ${box.y} ${box.width} ${box.height}`);
      });
    // 지도 조작은 프레임별로 반영하고 타일·후보 조회용 카메라 보고는 합친다.
    if (reportTimer.current !== null) clearTimeout(reportTimer.current);
    reportTimer.current = window.setTimeout(() => {
      reportTimer.current = null;
      setView(current.current);
      onCamera(current.current);
    }, 200);
  }
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      const matrix = element.getScreenCTM();
      if (!matrix) return;
      event.preventDefault();
      const anchor = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      const box = element.viewBox.baseVal;
      const u = (anchor.x - box.x) / box.width - 0.5;
      const v = (anchor.y - box.y) / box.height - 0.5;
      const pixels =
        event.deltaY *
        (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1);
      const currentBox = planBox(current.current, aspectRef.current);
      change(
        zoomPlanView(
          current.current,
          [
            current.current.center[0] + u * currentBox.width,
            current.current.center[1] - v * currentBox.height,
          ],
          Math.exp(Math.max(-500, Math.min(500, pixels)) * 0.002)
        )
      );
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => {
      element.removeEventListener('wheel', wheel);
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      if (reportTimer.current !== null) clearTimeout(reportTimer.current);
      frame.current = null;
      reportTimer.current = null;
    };
  }, [onCamera, onNavigate]);
  function pointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 || !event.isPrimary) return;
    const matrix = svg.current?.getScreenCTM();
    if (!matrix) return;
    moved.current = false;
    drag.current = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      scale: 1 / matrix.a,
      view: current.current,
    };
  }
  function pointerMove(event: PointerEvent<SVGSVGElement>) {
    const start = drag.current;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x,
      dy = event.clientY - start.y;
    if (!moved.current && Math.hypot(dx, dy) <= 5) return;
    moved.current = true;
    setDragging(true);
    svg.current?.setPointerCapture(event.pointerId);
    change({
      ...start.view,
      center: [start.view.center[0] - dx * start.scale, start.view.center[1] + dy * start.scale],
      distance: start.view.distance,
    });
  }
  function pointerEnd(event: PointerEvent<SVGSVGElement>) {
    if (drag.current?.id !== event.pointerId) return;
    if (svg.current?.hasPointerCapture(event.pointerId))
      svg.current.releasePointerCapture(event.pointerId);
    drag.current = null;
    setDragging(false);
  }
  return {
    svg,
    view,
    box: planBox(view, aspect),
    dragging,
    handlers: {
      onPointerDown: pointerDown,
      onPointerMove: pointerMove,
      onPointerUp: pointerEnd,
      onPointerCancel: pointerEnd,
      onClickCapture: (event: React.MouseEvent) => {
        if (moved.current && event.detail !== 0) {
          event.preventDefault();
          event.stopPropagation();
        }
        moved.current = false;
      },
    },
  };
}
