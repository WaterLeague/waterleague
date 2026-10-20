import { useEffect, useRef, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useThree } from '@react-three/fiber';

export function SceneHtmlLayer({ children, zIndex }: { children: ReactNode; zIndex: number }) {
  const gl = useThree((state) => state.gl);
  const root = useRef<Root | null>(null);
  useEffect(() => {
    const container = document.createElement('div');
    container.style.cssText = `position:absolute;inset:0;pointer-events:none;z-index:${zIndex};`;
    gl.domElement.parentElement?.append(container);
    const current = createRoot(container);
    root.current = current;
    return () => {
      if (root.current === current) root.current = null;
      // 3D 트리의 정리가 끝난 뒤 별도 DOM 루트를 해제해 중첩 렌더 정리를 피한다.
      queueMicrotask(() => {
        current.unmount();
        container.remove();
      });
    };
  }, [gl, zIndex]);
  useEffect(() => {
    root.current?.render(children);
  }, [children, gl, zIndex]);
  return null;
}
