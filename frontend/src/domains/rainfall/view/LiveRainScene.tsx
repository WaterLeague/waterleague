import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { createRainGeometry, createRainMaterial } from '../service/rainGeometryService';
import type { UrbanTime } from '../../urban/entity/urban';
import { urbanAnimationTime } from '../../urban/service/urbanTimeService';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import type { City } from '../../city/entity/city';
import {
  rainParticleSeeds,
  rainAreaOverlaps,
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
  timeline,
}: {
  districts: City['districts'];
  amounts: ReadonlyMap<string, number | null>;
  center: [number, number];
  distance: number;
  animate: boolean;
  terrain?: Terrain | null;
  externalClock?: boolean;
  timeline?: UrbanTime;
}) {
  const animationTime = useRef(0);
  const invalidate = useThree((s) => s.invalidate);
  const { x, y, radius, scale } = rainSamplingWindow(center, distance);
  const near = distance < 9000;
  const seeds = useMemo(() => {
    const visible = districts.filter((d) => rainAreaOverlaps(d.polygons, x, y, radius));
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
  const geometry = useMemo(() => createRainGeometry(seeds, length), [seeds, length]);
  const { material, uniforms } = useMemo(createRainMaterial, []);
  useEffect(() => () => material.dispose(), [material]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => {
    if (externalClock || !animate || !seeds.length) return;
    invalidate();
    const timer = window.setInterval(invalidate, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [animate, seeds.length, invalidate, externalClock]);
  useFrame(({ clock }) => {
    if (timeline)
      animationTime.current = urbanAnimationTime(timeline, animationTime.current, animate);
    else if (animate) animationTime.current = clock.elapsedTime;
    // 입자 버퍼를 다시 전송하지 않고 같은 낙하 주기를 GPU에서 적용한다.
    uniforms.rainCycle.value = (animationTime.current / 1.7) % 1;
    uniforms.rainHeight.value = height;
  }, -0.15);
  return seeds.length ? (
    <lineSegments
      geometry={geometry}
      material={material}
      frustumCulled={false}
      raycast={() => {}}
    />
  ) : null;
}
