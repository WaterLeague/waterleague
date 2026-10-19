import { memo, useEffect, useState, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useUrbanLighting } from './UrbanEnvironment';
import type { MeshStandardMaterial } from 'three';
import { BufferAttribute, BufferGeometry, DoubleSide } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
export const StreetLayer = memo(function StreetLayer({
  roads,
  terrain,
  detail,
}: {
  roads: Street[];
  terrain: Terrain | null;
  detail: boolean;
}) {
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [failed, setFailed] = useState(false);
  const material = useRef<MeshStandardMaterial>(null),
    light = useUrbanLighting();
  useFrame(() => {
    if (material.current) material.current.emissiveIntensity = (light?.night.value ?? 0) * 0.05;
  }, -0.2);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  useEffect(() => {
    setFailed(false);
    const worker = new Worker(new URL('../service/streetGeometry.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = ({ data }) => {
      if (data.failed) {
        setFailed(true);
        worker.terminate();
        return;
      }
      const mesh = new BufferGeometry();
      mesh.setAttribute('position', new BufferAttribute(data.positions, 3));
      mesh.setAttribute('color', new BufferAttribute(data.colors, 3));
      mesh.computeVertexNormals();
      mesh.computeBoundingSphere();
      setGeometry(mesh);
      worker.terminate();
    };
    worker.onerror = () => {
      setFailed(true);
      worker.terminate();
    };
    worker.postMessage({ roads, terrain, detail });
    return () => {
      worker.terminate();
    };
  }, [roads, terrain, detail]);
  if (failed) throw new Error('도로 표시 실패');
  return geometry ? (
    <mesh geometry={geometry} receiveShadow raycast={() => {}}>
      <meshStandardMaterial
        ref={material}
        vertexColors
        emissive="#8493a5"
        roughness={0.95}
        side={DoubleSide}
      />
    </mesh>
  ) : null;
});
