import { useEffect, useRef } from 'react';
import { startHomeMotion } from '../service/homeMotionService';

export function useHomeMotion() {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (ref.current) return startHomeMotion(ref.current);
  }, []);
  return ref;
}
