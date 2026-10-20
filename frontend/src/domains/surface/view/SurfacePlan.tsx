import { memo, useMemo } from 'react';
import type { SurfaceFrame, SurfaceMetric } from '../entity/surface';
import { surfacePlanPaths } from '../service/surfaceGeometry';
import { surfaceDirectionPaths } from '../service/surfaceDirections';

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
