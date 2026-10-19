import { buildingRaycast } from '../../city/service/buildingRaycastService';
import { GeometryBufferCache } from '../../../shared/repository/geometryBufferCache';
import { Sphere, Vector3 } from 'three';
import { streetAtFace } from '../service/streetGeometryService';
import { memo, useEffect, useState, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useUrbanLighting } from './UrbanEnvironment';
import type { MeshStandardMaterial } from 'three';
import { BufferAttribute, BufferGeometry, DoubleSide } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import type { ParkingData } from '../entity/parking';
type StreetBuffers = {
  positions: Float32Array;
  colors: Float32Array;
  normals: Float32Array;
  bounds: Float32Array;
  ends: number[];
  sphere: number[];
};
const bufferCache = new GeometryBufferCache<StreetBuffers>();
const terrainIds = new WeakMap<object, number>();
let terrainId = 0;
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
    if (terrain && !terrainIds.has(terrain)) terrainIds.set(terrain, ++terrainId);
    if (parking && !terrainIds.has(parking)) terrainIds.set(parking, ++terrainId);
    const variant = `${terrain ? terrainIds.get(terrain) : 0}:${detail}:${parking ? terrainIds.get(parking) : 0}`;
    const apply = (data: StreetBuffers) => {
      const mesh = new BufferGeometry();
      mesh.setAttribute('position', new BufferAttribute(data.positions, 3));
      mesh.setAttribute('color', new BufferAttribute(data.colors, 3));
      mesh.setAttribute('normal', new BufferAttribute(data.normals, 3));
      mesh.userData.streetEnds = data.ends;
      mesh.userData.streetIds = roads.map((road) => road.id);
      mesh.userData.raycast = buildingRaycast(data);
      mesh.boundingSphere = new Sphere(new Vector3(...data.sphere.slice(0, 3)), data.sphere[3]);
      setGeometry(mesh);
    };
    const cached = bufferCache.get(roads, variant);
    if (cached) {
      apply(cached);
      return;
    }
    const worker = new Worker(new URL('../service/streetGeometry.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = ({ data }) => {
      if (data.failed) {
        setFailed(true);
        worker.terminate();
        return;
      }
      bufferCache.put(roads, variant, data);
      apply(data);
      worker.terminate();
    };
    const fail = () => {
      setFailed(true);
      worker.terminate();
    };
    worker.onerror = fail;
    worker.onmessageerror = fail;
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
      raycast={onStreet ? geometry.userData.raycast : () => {}}
      onClick={
        onStreet
          ? (event) => {
              if (event.delta > 4) return;
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
