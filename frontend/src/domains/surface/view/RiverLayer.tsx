import { memo, useEffect, useState } from 'react';
import { BufferAttribute, BufferGeometry } from 'three';
import type { City } from '../../city/entity/city';
import type { Terrain } from '../../terrain/entity/terrain';
import type { WaterWeather } from '../service/waterAppearanceService';
import type { riverGeometry } from '../service/riverGeometry';
import { WaterMaterial } from './WaterMaterial';
import { useWaterObject } from './WaterScene';
export const RiverLayer = memo(function RiverLayer({
  city,
  terrain,
  weather,
}: {
  city: City;
  terrain: Terrain | null;
  weather: WaterWeather;
}) {
  const waterRef = useWaterObject();
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setGeometry(null);
    setFailed(false);
    let mesh: BufferGeometry | null = null;
    const worker = new Worker(new URL('../service/riverGeometry.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = (
      event: MessageEvent<ReturnType<typeof riverGeometry> & { failed?: boolean }>
    ) => {
      if (event.data.failed) {
        setFailed(true);
        worker.terminate();
        return;
      }
      const { positions, colors, flows, depths, faces } = event.data;
      mesh = new BufferGeometry();
      mesh.setAttribute('position', new BufferAttribute(positions, 3));
      mesh.setAttribute('color', new BufferAttribute(colors, 3));
      mesh.setAttribute('flow', new BufferAttribute(flows, 2));
      mesh.setAttribute('waterDepth', new BufferAttribute(depths, 1));
      mesh.setAttribute('waterFace', new BufferAttribute(faces, 1));
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
      surfaces: city.surfaces.filter((s) => s.kind === 'water').map((s) => s.polygons),
      terrain,
    });
    return () => {
      worker.terminate();
      mesh?.dispose();
    };
  }, [city, terrain]);
  if (failed) throw new Error('수면 형상 표시 실패');
  return geometry ? (
    <mesh
      ref={waterRef}
      geometry={geometry}
      renderOrder={3}
      raycast={() => {}}
      userData={{ naturalWater: true }}
    >
      <WaterMaterial natural weather={weather} />
    </mesh>
  ) : null;
});
