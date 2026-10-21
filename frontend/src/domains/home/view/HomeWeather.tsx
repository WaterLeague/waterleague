import { useEffect, useLayoutEffect, useMemo, useRef, type RefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  Color,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  type AmbientLight,
  type DirectionalLight,
  type Group,
  type Mesh,
} from 'three';
import { rainParticleSeeds, type RainPolygons } from '../../rainfall/service/rainEffectService';
import { createRainGeometry, createRainMaterial } from '../../rainfall/service/rainGeometryService';
import {
  previewElapsed,
  previewWeather,
  type PreviewTimeline,
} from '../service/homePreviewService';

const RAIN_AREA: RainPolygons = [
  [
    [
      [-2.5, -1.9],
      [2.5, -1.9],
      [2.5, 1.9],
      [-2.5, 1.9],
      [-2.5, -1.9],
    ],
  ],
];
const DAY_SKY = new Color('#edf4ee');
const NIGHT_SKY = new Color('#172b46');
const RAIN_SKY = new Color('#899ba5');
const DAY_RAIN = new Color('#365f75');
const NIGHT_RAIN = new Color('#a7cde5');
const WARM_SUN = new Color('#ffd2a0');
const HIGH_SUN = new Color('#fff7e6');

export function HomeWeather({
  mode,
  timeline,
  running,
}: {
  mode: 'weekly' | 'disaster';
  timeline: RefObject<PreviewTimeline>;
  running: boolean;
}) {
  const invalidate = useThree((state) => state.invalidate);
  const scene = useThree((state) => state.scene);
  const ambient = useRef<AmbientLight>(null);
  const sunlight = useRef<DirectionalLight>(null);
  const sun = useRef<MeshBasicMaterial>(null);
  const sunDisk = useRef<Mesh>(null);
  const sunTarget = useMemo(() => new Object3D(), []);
  const moon = useRef<MeshBasicMaterial>(null);
  const clouds = useRef<Group>(null);
  const cloudMaterial = useMemo(
    () => new MeshStandardMaterial({ color: '#adbdcd', transparent: true, depthWrite: false }),
    []
  );
  const windows = useMemo(
    () => new MeshBasicMaterial({ color: '#f6d590', transparent: true, depthWrite: false }),
    []
  );
  const sky = useMemo(() => new Color(), []);
  const rain = useMemo(() => {
    const seeds = rainParticleSeeds(RAIN_AREA, [0, 0], 4, 180).map((seed) => ({
      ...seed,
      elevation: 0.06,
    }));
    return { geometry: createRainGeometry(seeds, 0.16), ...createRainMaterial() };
  }, []);

  useLayoutEffect(() => {
    const previous = scene.background;
    scene.background = sky;
    return () => {
      scene.background = previous;
    };
  }, [scene, sky]);
  useEffect(
    () => () => {
      rain.geometry.dispose();
      rain.material.dispose();
      cloudMaterial.dispose();
      windows.dispose();
    },
    [rain, cloudMaterial, windows]
  );
  useEffect(() => {
    invalidate();
    if (!running) return;
    // GPU 입자는 그대로 두고 보이는 미리보기만 초당 30번 갱신한다.
    const timer = window.setInterval(invalidate, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [running, invalidate]);

  useFrame(() => {
    const elapsed = previewElapsed(timeline.current, performance.now());
    const { day, rain: wet, solar } = previewWeather(mode, timeline.current.epoch, elapsed);
    sky
      .copy(NIGHT_SKY)
      .lerp(DAY_SKY, day)
      .lerp(RAIN_SKY, wet * day * 0.55);
    if (ambient.current) ambient.current.intensity = 0.5 + day * 1.1;
    if (sunlight.current) {
      if (solar) {
        sunlight.current.position.set(...solar.direction).multiplyScalar(6);
        sunlight.current.intensity =
          Math.max(0, Math.min(1, solar.elevation / 12)) * 2.5 * (1 - wet * 0.4);
        sunlight.current.color
          .copy(WARM_SUN)
          .lerp(HIGH_SUN, Math.max(0, Math.min(1, solar.elevation / 25)));
      } else sunlight.current.intensity = 0.2 + day * (2.1 - wet * 0.8);
    }
    if (sunDisk.current && solar) {
      // 작은 모형의 하늘 안에 태양의 방위·고도 변화를 담는다.
      const [east, up, south] = solar.direction;
      sunDisk.current.position.set(east * 2.8, 1.6 + up * 1.6, -1.8 + south * 0.5);
      sunDisk.current.visible = solar.elevation > -0.83;
    }
    if (sun.current) sun.current.opacity = day * (1 - wet);
    if (moon.current) moon.current.opacity = (1 - day) * (1 - wet * 0.7);
    if (clouds.current) clouds.current.visible = wet > 0.001;
    cloudMaterial.opacity = wet * 0.95;
    windows.opacity = (1 - day) * 0.95;
    rain.uniforms.rainHeight.value = 2.8;
    rain.uniforms.rainCycle.value = elapsed / 0.9;
    rain.material.opacity = wet * 0.65;
    rain.material.color.copy(NIGHT_RAIN).lerp(DAY_RAIN, day);
  });

  return (
    <>
      <ambientLight ref={ambient} intensity={1.5} />
      <primitive object={sunTarget} />
      <directionalLight ref={sunlight} target={sunTarget} position={[4, 6, 3]} intensity={2.2} />
      <directionalLight position={[-3, 2, -2]} intensity={0.6} color="#c1dbed" />
      {mode === 'weekly' && (
        <>
          <mesh ref={sunDisk}>
            <sphereGeometry args={[0.42, 20, 16]} />
            <meshBasicMaterial ref={sun} color="#f4cd68" transparent depthWrite={false} />
          </mesh>
          <mesh position={[-1.6, 2.6, -1.2]}>
            <sphereGeometry args={[0.3, 20, 16]} />
            <meshBasicMaterial ref={moon} color="#dfedf5" transparent depthWrite={false} />
          </mesh>
          {[1.35, 1.6, 1.85].flatMap((x) =>
            [0.35, 0.7].map((y) => (
              <mesh key={`${x}-${y}`} position={[x, y, -0.441]} material={windows}>
                <planeGeometry args={[0.12, 0.17]} />
              </mesh>
            ))
          )}
        </>
      )}
      <group ref={clouds}>
        {(
          [
            [-1.2, 2.8, -0.5],
            [0, 2.95, -0.4],
            [0.95, 2.75, -0.5],
          ] as const
        ).map(([x, y, z]) => (
          <mesh key={x} position={[x, y, z]} scale={[1, 0.48, 0.55]} material={cloudMaterial}>
            <sphereGeometry args={[0.85, 16, 12]} />
          </mesh>
        ))}
      </group>
      <lineSegments
        geometry={rain.geometry}
        material={rain.material}
        frustumCulled={false}
        raycast={() => {}}
      />
    </>
  );
}
