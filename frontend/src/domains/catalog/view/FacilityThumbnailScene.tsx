import { useEffect, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { Box } from 'lucide-react';
import type { FacilityType } from '../../game/entity/game';
import { facilitySymbolGeometry } from '../service/facilitySymbolService';

function Model({ type }: { type: FacilityType }) {
  const geometry = useMemo(() => facilitySymbolGeometry(type), [type]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <group position={[0, -0.45, 0]}>
      <mesh geometry={geometry}>
        <meshStandardMaterial vertexColors roughness={0.85} />
      </mesh>
      <mesh position={[0, -0.12, 0]}>
        <boxGeometry args={[2.6, 0.2, 2.1]} />
        <meshStandardMaterial color="#d8cdb6" roughness={1} />
      </mesh>
    </group>
  );
}

export default function FacilityThumbnailScene({ type }: { type: FacilityType }) {
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 1.5]}
      camera={{ position: [3.6, 2.9, 4.2], fov: 36 }}
      gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
      fallback={<Box size={30} />}
    >
      <ambientLight intensity={1.5} />
      <directionalLight position={[4, 6, 3]} intensity={2.2} />
      <directionalLight position={[-3, 2, -2]} intensity={0.6} color="#c1dbed" />
      <Model type={type} />
    </Canvas>
  );
}
