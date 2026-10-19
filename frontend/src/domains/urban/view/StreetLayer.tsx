import { streetAtFace } from '../service/streetGeometryService';
import { memo, useEffect, useState, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useUrbanLighting } from './UrbanEnvironment';
import type { MeshStandardMaterial } from 'three';
import { BufferAttribute, BufferGeometry, DoubleSide, Mesh } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import type { ParkingData } from '../entity/parking';
export const StreetLayer = memo(function StreetLayer({
  roads,
  terrain,
  detail,
  parking,
  onStreet,
}: {
  roads: Street[];
  terrain: Terrain | null;
  detail: boolean;
  parking?: ParkingData | null;
  onStreet?: (sourceId: string, point: [number, number]) => void;
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
      mesh.userData.streetEnds = data.ends;
      mesh.userData.streetIds = roads.map((road) => road.id);
      mesh.computeVertexNormals();
      mesh.computeBoundingSphere();
      setGeometry(mesh);
      worker.terminate();
    };
    worker.onerror = () => {
      setFailed(true);
      worker.terminate();
    };
    worker.postMessage({
      roads,
      terrain,
      detail,
      parkingAisles:
        parking?.routes
          .filter((route) => route.reason === 'OSM_PARKING_AISLE')
          .map((route) => route.id) ?? [],
    });
    return () => {
      worker.terminate();
    };
  }, [roads, terrain, detail, parking]);
  if (failed) throw new Error('도로 표시 실패');
  return geometry ? (
    <mesh
      geometry={geometry}
      receiveShadow
      raycast={onStreet ? Mesh.prototype.raycast : () => {}}
      onClick={
        onStreet
          ? (event) => {
              const index = streetAtFace(geometry.userData.streetEnds, event.faceIndex ?? -1);
              if (index < 0) return;
              event.stopPropagation();
              onStreet(geometry.userData.streetIds[index], [event.point.x, -event.point.z]);
            }
          : undefined
      }
    >
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
