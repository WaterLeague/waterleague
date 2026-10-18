import { memo, useEffect, useMemo, useState } from 'react';
import * as THREE from 'three';
import type { SurfaceFrame, SurfaceMetric } from '../entity/surface';
import type { Terrain } from '../../terrain/entity/terrain';
import { surfacePlanPaths } from '../service/surfaceGeometry';
import { surfaceDirectionPaths } from '../service/surfaceDirections';
export const SurfaceLayer = memo(function SurfaceLayer({
  frame,
  metric,
  terrain,
  onError,
}: {
  frame: SurfaceFrame | null;
  metric: SurfaceMetric;
  terrain: Terrain | null;
  onError: () => void;
}) {
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
      event: MessageEvent<{ positions?: Float32Array; colors?: Float32Array }>
    ) => {
      if (!event.data.positions || !event.data.colors) {
        onError();
        worker.terminate();
        return;
      }
      mesh = new THREE.BufferGeometry();
      mesh.setAttribute('position', new THREE.BufferAttribute(event.data.positions, 3));
      mesh.setAttribute('color', new THREE.BufferAttribute(event.data.colors, 3));
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
    <mesh geometry={geometry.mesh} renderOrder={31} raycast={() => {}}>
      <meshBasicMaterial
        vertexColors
        toneMapped={false}
        fog={false}
        transparent
        opacity={0.72}
        depthTest={false}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  ) : null;
});
export const SurfacePlan = memo(function SurfacePlan({
  frame,
  metric,
}: {
  frame: SurfaceFrame | null;
  metric: SurfaceMetric;
}) {
  const paths = useMemo(() => (frame ? surfacePlanPaths(frame, metric) : []), [frame, metric]);
  const arrows = useMemo(
    () => (frame && metric === 'speed' ? surfaceDirectionPaths(frame) : []),
    [frame, metric]
  );
  return (
    <g pointerEvents="none" opacity={0.72}>
      {paths.map((p) => (
        <path key={p.color} d={p.path} fill={p.color} />
      ))}
      {arrows.map((p) => (
        <path key={p.triangleId} data-flow-direction={p.triangleId} d={p.path} fill={p.color} />
      ))}
    </g>
  );
});
