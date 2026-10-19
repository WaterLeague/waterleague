import { useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import type { City } from '../../city/entity/city';
import {
  rainParticleSeeds,
  rainSamplingWindow,
  rainVisualDensity,
} from '../service/rainEffectService';

export function LiveRainScene({
  districts,
  amounts,
  center,
  distance,
  animate,
  terrain,
  externalClock = false,
}: {
  districts: City['districts'];
  amounts: ReadonlyMap<string, number | null>;
  center: [number, number];
  distance: number;
  animate: boolean;
  terrain?: Terrain | null;
  externalClock?: boolean;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const { x, y, radius, scale } = rainSamplingWindow(center, distance);
  const near = distance < 9000;
  const seeds = useMemo(() => {
    const visible = districts.filter((d) =>
      d.polygons.some((polygon) => {
        const xs = polygon[0].map((p) => p[0]),
          ys = polygon[0].map((p) => p[1]);
        return (
          Math.max(...xs) >= x - radius &&
          Math.min(...xs) <= x + radius &&
          Math.max(...ys) >= y - radius &&
          Math.min(...ys) <= y + radius
        );
      })
    );
    const counts = visible.map((d) =>
      Math.round((near ? 1000 : 200) * rainVisualDensity(amounts.get(d.id)))
    );
    const cap = Math.min(
      1,
      6000 /
        Math.max(
          1,
          counts.reduce((a, b) => a + b, 0)
        )
    );
    return visible
      .flatMap((d, i) => rainParticleSeeds(d.polygons, [x, y], radius, Math.floor(counts[i] * cap)))
      .map((s) => ({ ...s, elevation: terrainHeight(terrain, s.point) }));
  }, [districts, amounts, x, y, radius, near, terrain]);
  const height = Math.max(120, Math.min(1800, scale * 0.3));
  const length = Math.max(3.5, Math.min(height * 0.2, scale * 0.018));
  const geometry = useMemo(() => {
    const value = new THREE.BufferGeometry();
    const initial = new Float32Array(seeds.length * 6);
    seeds.forEach(({ point: [x, y], phase, elevation }, i) => {
      const top = elevation + height * (1 - phase);
      initial.set([x, top + length, -y, x, top, -y], i * 6);
    });
    value.setAttribute('position', new THREE.BufferAttribute(initial, 3));
    return value;
  }, [seeds, height, length]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => {
    if (externalClock || !animate || !seeds.length) return;
    invalidate();
    const timer = window.setInterval(invalidate, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [animate, seeds.length, invalidate, externalClock]);
  useFrame(({ clock }) => {
    if (!animate) return;
    const positions = geometry.getAttribute('position') as THREE.BufferAttribute;
    seeds.forEach(({ point: [x, y], phase, elevation }, i) => {
      const top = elevation + height * (1 - ((clock.elapsedTime / 1.7 + phase) % 1));
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
