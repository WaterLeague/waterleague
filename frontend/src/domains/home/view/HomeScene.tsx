import {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type ReactNode,
  type RefObject,
} from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { Group } from 'three';
import type { FacilityType } from '../../game/entity/game';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { facilitySymbolGeometry } from '../../catalog/service/facilitySymbolService';
import { useReducedMotion } from '../../catalog/controller/useReducedMotion';
import { HomeWeather } from './HomeWeather';
import type { PreviewTimeline } from '../service/homePreviewService';
import { HomeFloodRecord, HomeInfrastructureSymbol } from './HomeMapObjects';
import { WaterScene } from '../../surface/view/WaterScene';

function Turntable({
  angle,
  selection,
  height,
  children,
}: {
  angle: number;
  selection: string;
  height: number;
  children: ReactNode;
}) {
  const group = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);
  const reduced = useReducedMotion();
  useLayoutEffect(() => {
    if (group.current) group.current.scale.setScalar(reduced ? 1 : 0.92);
    invalidate();
  }, [selection, reduced, invalidate]);
  useLayoutEffect(() => {
    if (reduced && group.current) group.current.rotation.y = angle;
    invalidate();
  }, [angle, reduced, invalidate]);
  useFrame((_, delta) => {
    const target = group.current;
    if (!target || reduced) return;
    const step = 1 - Math.exp(-Math.min(delta, 0.05) * 12);
    target.rotation.y += (angle - target.rotation.y) * step;
    target.scale.setScalar(target.scale.x + (1 - target.scale.x) * step);
    // 전환이 끝나면 다음 프레임 요청을 끊어 유휴 GPU 사용을 막는다.
    if (Math.abs(angle - target.rotation.y) > 0.001 || 1 - target.scale.x > 0.001) invalidate();
    else {
      target.rotation.y = angle;
      target.scale.setScalar(1);
    }
  });
  return (
    <group ref={group} position={[0, height, 0]}>
      {children}
    </group>
  );
}

function Facility({
  type,
  position = [0, 0, 0],
  scale = 1,
}: {
  type: FacilityType;
  position?: [number, number, number];
  scale?: number;
}) {
  const geometry = useMemo(() => facilitySymbolGeometry(type), [type]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} position={position} scale={scale}>
      <meshStandardMaterial vertexColors roughness={0.85} />
    </mesh>
  );
}

function Block({
  position,
  size,
  color,
}: {
  position: [number, number, number];
  size: [number, number, number];
  color: string;
}) {
  return (
    <mesh position={position}>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.85} />
    </mesh>
  );
}

function Neighborhood() {
  return (
    <group>
      <Block position={[0, -0.22, 0]} size={[5, 0.42, 3.8]} color="#9eb78c" />
      <Block position={[0, 0.01, 0.58]} size={[5.02, 0.05, 0.64]} color="#91a0a0" />
      {[-1.8, -0.6, 0.6, 1.8].map((x) => (
        <Block key={x} position={[x, 0.05, 0.58]} size={[0.48, 0.015, 0.045]} color="#f8f0d0" />
      ))}
      <Facility type="GREEN_ROOF" position={[-1.15, 0, -0.8]} scale={0.85} />
      <Facility type="RAINWATER_CISTERN" position={[0.5, 0, -1]} scale={0.65} />
      <Facility type="RAIN_GARDEN" position={[1.55, 0, 1.35]} scale={0.6} />
      <Facility type="PERMEABLE_PAVEMENT" position={[-1.1, 0, 1.4]} scale={0.6} />
      <Block position={[1.6, 0.5, -0.9]} size={[0.85, 1, 0.9]} color="#e7d5b8" />
    </group>
  );
}

const HomeScene = memo(function HomeScene({
  mode,
  map,
  infrastructure = 'STORM_PUMP',
  facility,
  angle,
  timeline,
  running,
}: {
  mode?: 'weekly' | 'disaster';
  map?: 'flood' | 'infrastructure';
  infrastructure?: InfrastructureAsset['kind'];
  facility: FacilityType;
  angle: number;
  timeline: RefObject<PreviewTimeline>;
  running: boolean;
}) {
  const neighborhood = !!mode || map === 'flood';
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 1.5]}
      camera={{ position: neighborhood ? [6, 4.5, 7] : [3.6, 2.9, 4.2], fov: 38 }}
      gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
      fallback={<p>이 기기에서는 3D 미리보기를 지원하지 않습니다.</p>}
    >
      {!mode && (
        <>
          <ambientLight intensity={1.5} />
          <directionalLight position={[4, 6, 3]} intensity={2.2} />
          <directionalLight position={[-3, 2, -2]} intensity={0.6} color="#c1dbed" />
        </>
      )}
      <Turntable
        angle={angle}
        selection={map === 'infrastructure' ? infrastructure : facility}
        height={neighborhood ? -0.6 : -0.45}
      >
        {mode ? (
          <>
            <Neighborhood />
            <HomeWeather mode={mode} timeline={timeline} running={running} />
          </>
        ) : map === 'flood' ? (
          <WaterScene animate={false}>
            <Neighborhood />
            <HomeFloodRecord />
          </WaterScene>
        ) : (
          <>
            <Block position={[0, -0.14, 0]} size={[2.8, 0.24, 2.4]} color="#d6c9ac" />
            {map === 'infrastructure' ? (
              <HomeInfrastructureSymbol kind={infrastructure} />
            ) : (
              <Facility type={facility} />
            )}
          </>
        )}
      </Turntable>
      <OrbitControls
        enableZoom={false}
        enablePan={false}
        enableDamping={false}
        minPolarAngle={0.4}
        maxPolarAngle={Math.PI / 2.2}
        target={[0, 0.45, 0]}
      />
    </Canvas>
  );
});

export default HomeScene;
