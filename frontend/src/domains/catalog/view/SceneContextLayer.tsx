import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import type { SceneContext } from '../entity/sceneContext';
import { polygonShapes } from '../service/mapGeometryService';
import { sceneSurfaceStyle } from '../service/sceneContextService';
import { LabelMarker } from './SceneLabels';

function SurfaceLayer({
  context,
  kind,
}: {
  context: SceneContext;
  kind: keyof typeof sceneSurfaceStyle;
}) {
  const geometry = useMemo(
    () =>
      new THREE.ShapeGeometry(
        polygonShapes(context.features.filter((f) => f.kind === kind).flatMap((f) => f.polygons))
      ),
    [context, kind]
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  const style = sceneSurfaceStyle[kind];
  return (
    <mesh
      geometry={geometry}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, style.elevation, 0]}
      receiveShadow
      raycast={() => {}}
    >
      <meshStandardMaterial
        color={style.color}
        roughness={style.roughness}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}
export function SceneContextLayer({ context, labels }: { context: SceneContext; labels: boolean }) {
  return (
    <group>
      {(Object.keys(sceneSurfaceStyle) as (keyof typeof sceneSurfaceStyle)[]).map((kind) => (
        <SurfaceLayer key={kind} kind={kind} context={context} />
      ))}
      {labels &&
        context.labels.map((label) => (
          <LabelMarker
            key={label.name}
            text={label.name}
            position={[label.center[0], 0.1, -label.center[1]]}
          />
        ))}
    </group>
  );
}
