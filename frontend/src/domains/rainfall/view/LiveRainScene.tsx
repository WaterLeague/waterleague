import { useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { City } from '../../city/entity/city';
import { rainParticleSeeds } from '../service/rainEffectService';

export function LiveRainScene({
  districts,
  center,
  distance,
  animate,
}: {
  districts: City['districts'];
  center: [number, number];
  distance: number;
  animate: boolean;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const seeds = useMemo(() => {
    const visible = districts.filter((d) =>
      d.polygons.some((polygon) => {
        const xs = polygon[0].map((p) => p[0]),
          ys = polygon[0].map((p) => p[1]);
        return (
          Math.max(...xs) >= center[0] - distance &&
          Math.min(...xs) <= center[0] + distance &&
          Math.max(...ys) >= center[1] - distance &&
          Math.min(...ys) <= center[1] + distance
        );
      })
    );
    const count =
      distance < 9000 ? Math.min(1200, Math.floor(6000 / Math.max(1, visible.length))) : 240;
    return visible.flatMap((d) => rainParticleSeeds(d.polygons, center, distance, count));
  }, [districts, center, distance]);
  const geometry = useMemo(() => {
    const value = new THREE.BufferGeometry();
    const height = Math.max(120, Math.min(1800, distance * 0.3));
    const length = Math.max(3.5, Math.min(height * 0.2, distance * 0.018));
    const initial = new Float32Array(seeds.length * 6);
    seeds.forEach(({ point: [x, y], phase }, i) => {
      const top = height * (1 - phase);
      initial.set([x, top + length, -y, x, top, -y], i * 6);
    });
    value.setAttribute('position', new THREE.BufferAttribute(initial, 3));
    return value;
  }, [seeds, distance]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => {
    if (!animate || !seeds.length) return;
    invalidate();
    const timer = window.setInterval(invalidate, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [animate, seeds.length, invalidate]);
  useFrame(({ clock }) => {
    if (!animate) return;
    const height = Math.max(120, Math.min(1800, distance * 0.3));
    const length = Math.max(3.5, Math.min(height * 0.2, distance * 0.018));
    const positions = geometry.getAttribute('position') as THREE.BufferAttribute;
    seeds.forEach(({ point: [x, y], phase }, i) => {
      const top = height * (1 - ((clock.elapsedTime / 1.7 + phase) % 1));
      positions.setXYZ(i * 2, x, top + length, -y);
      positions.setXYZ(i * 2 + 1, x, top, -y);
    });
    positions.needsUpdate = true;
  });
  return seeds.length ? (
    <lineSegments geometry={geometry} frustumCulled={false} raycast={() => {}}>
      <lineBasicMaterial color="#365f75" transparent opacity={0.65} depthWrite={false} />
    </lineSegments>
  ) : null;
}
