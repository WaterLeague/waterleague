import { memo } from 'react';
import type { CisternGeometryPreview } from '../dto/cisternLayoutDto';
export const CisternLayoutPlan = memo(function CisternLayoutPlan({
  geometry: g,
}: {
  geometry: CisternGeometryPreview;
}) {
  const angle = (g.rotationDeg * Math.PI) / 180,
    c = Math.cos(angle),
    s = Math.sin(angle);
  const inner = [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ].map(([a, b]) => [
    g.center[0] + (c * a * g.internalWidthM) / 2 - (s * b * g.internalLengthM) / 2,
    g.center[1] + (s * a * g.internalWidthM) / 2 + (c * b * g.internalLengthM) / 2,
  ]);
  const path = (points: number[][]) =>
    points.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' ') + 'Z';
  return (
    <g pointerEvents="none" aria-label="이용조 설계 외곽">
      <path
        d={path(g.coordinates)}
        fill={g.contained ? '#d4a653' : '#d86a55'}
        fillOpacity={0.35}
        stroke={g.contained ? '#7d552a' : '#b53b29'}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      <path
        d={path(inner)}
        fill="none"
        stroke={g.contained ? '#7d552a' : '#b53b29'}
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
      <title>설계 외곽 · 현재 수위 아님</title>
    </g>
  );
});
