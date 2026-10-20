import { memo, useEffect, useState } from 'react';
import * as THREE from 'three';
import type { SurfaceFrame, SurfaceMetric } from '../entity/surface';
import type { Terrain } from '../../terrain/entity/terrain';
import { WaterMaterial } from './WaterMaterial';
import { useWaterObject } from './WaterScene';
import { calmWater, type WaterWeather } from '../service/waterAppearanceService';
export const SurfaceLayer = memo(function SurfaceLayer({
  frame,
  metric,
  terrain,
  onError,
  weather = calmWater,
}: {
  frame: SurfaceFrame | null;
  metric: SurfaceMetric;
  terrain: Terrain | null;
  onError: () => void;
  weather?: WaterWeather;
}) {
  const waterRef = useWaterObject();
  const [geometry, setGeometry] = useState<{
    frame: SurfaceFrame;
    metric: SurfaceMetric;
    mesh: THREE.BufferGeometry;
  } | null>(null);
  useEffect(() => {
    setGeometry(null);
    if (!frame) return;
    let mesh: THREE.BufferGeometry | null = null;
    const worker = new Worker(new URL('../service/surfaceGeometry.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = (
      event: MessageEvent<{
        positions?: Float32Array;
        colors?: Float32Array;
        flows?: Float32Array;
        depths?: Float32Array;
        faces?: Float32Array;
      }>
    ) => {
      if (
        !event.data.positions ||
        !event.data.colors ||
        !event.data.flows ||
        !event.data.depths ||
        !event.data.faces
      ) {
        onError();
        worker.terminate();
        return;
      }
      mesh = new THREE.BufferGeometry();
      mesh.setAttribute('position', new THREE.BufferAttribute(event.data.positions, 3));
      mesh.setAttribute('color', new THREE.BufferAttribute(event.data.colors, 3));
      mesh.setAttribute('flow', new THREE.BufferAttribute(event.data.flows, 2));
      mesh.setAttribute('waterDepth', new THREE.BufferAttribute(event.data.depths, 1));
      mesh.setAttribute('waterFace', new THREE.BufferAttribute(event.data.faces, 1));
      mesh.computeVertexNormals();
      mesh.computeBoundingSphere();
      setGeometry({ frame, metric, mesh });
      worker.terminate();
    };
    worker.onerror = () => {
      onError();
      worker.terminate();
    };
    worker.postMessage({ frame, metric, terrain });
    return () => {
      worker.terminate();
      mesh?.dispose();
    };
  }, [frame, metric, terrain, onError]);
  return geometry?.frame === frame && geometry?.metric === metric ? (
    <mesh ref={waterRef} geometry={geometry.mesh} renderOrder={31} raycast={() => {}}>
      <WaterMaterial weather={weather} />
    </mesh>
  ) : null;
});
