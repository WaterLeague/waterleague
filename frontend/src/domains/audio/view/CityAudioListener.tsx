import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Vector3 } from 'three';
import type { AudioHandle } from '../entity/audio';

export function CityAudioListener({ audio }: { audio: AudioHandle }) {
  const direction = useMemo(() => new Vector3(), []);
  const up = useMemo(() => new Vector3(), []);
  const last = useRef(0);
  useFrame(({ camera }) => {
    if (!audio.current?.active || performance.now() - last.current < 80) return;
    last.current = performance.now();
    camera.getWorldDirection(direction);
    up.set(0, 1, 0).applyQuaternion(camera.quaternion);
    audio.current.listener(camera.position.toArray(), direction.toArray(), up.toArray());
  });
  return null;
}
