import { memo, useEffect, useState } from 'react';
import * as THREE from 'three';
import type { TraceTile } from '../entity/floodTrace';
import type { Terrain } from '../../terrain/entity/terrain';
import { traceColor } from '../service/floodTraceService';

export const FloodTraceLayer = memo(function FloodTraceLayer({
  tiles,
  terrain,
  onError,
}: {
  tiles: TraceTile[];
  terrain: Terrain | null;
  onError: () => void;
}) {
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);
  useEffect(() => {
    if (!tiles.length) {
      setGeometry(null);
      return;
    }
    setGeometry(null);
    let mesh: THREE.BufferGeometry | null = null;
    const worker = new Worker(new URL('../service/traceGeometry.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = (event: MessageEvent<{ positions?: Float32Array; failed?: boolean }>) => {
      if (!event.data.positions) {
        worker.terminate();
        onError();
        return;
      }
      mesh = new THREE.BufferGeometry();
      mesh.setAttribute('position', new THREE.BufferAttribute(event.data.positions, 3));
      mesh.computeBoundingSphere();
      setGeometry(mesh);
      worker.terminate();
    };
    worker.onerror = () => {
      worker.terminate();
      onError();
    };
    worker.postMessage({
      tiles: tiles.map((t) => ({ triangleVertices: t.triangleVertices })),
      terrain,
    });
    return () => {
      worker.terminate();
      mesh?.dispose();
    };
  }, [tiles, terrain, onError]);
  // 지표에 투영한 기록 범위이며 침수심 높이로 돌출하지 않는다.
  return geometry && tiles.length ? (
    <mesh geometry={geometry} renderOrder={30} raycast={() => {}}>
      <meshBasicMaterial
        color={traceColor}
        transparent
        opacity={0.48}
        depthTest={false}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  ) : null;
});

export const FloodTracePlan = memo(function FloodTracePlan({ tiles }: { tiles: TraceTile[] }) {
  return (
    <g pointerEvents="none" fill={traceColor} opacity={0.48} fillRule="evenodd">
      {tiles.map((t) => (
        <path key={`${t.eventId}/${t.id}`} d={t.path} />
      ))}
    </g>
  );
});
