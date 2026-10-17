import { useId, useMemo } from 'react';
import type { City } from '../../city/entity/city';
import { polygonPath } from '../../catalog/service/mapGeometryService';

export function LiveRainPlan({
  districts,
  scale,
  animate,
}: {
  districts: City['districts'];
  scale: number;
  animate: boolean;
}) {
  const id = useId().replace(/:/g, '');
  const paths = useMemo(
    () => districts.map((d) => ({ id: d.id, path: polygonPath(d.polygons) })),
    [districts]
  );
  const spacing = Math.max(10, scale * 0.016);
  return (
    <g pointerEvents="none" aria-hidden="true">
      <defs>
        <pattern id={id} width={spacing} height={spacing * 1.6} patternUnits="userSpaceOnUse">
          <g
            className={animate ? 'live-rain-streaks' : ''}
            style={{ '--rain-step': `${spacing * 1.6}px` } as React.CSSProperties}
          >
            {[-1, 0, 1].map((row) => (
              <path
                key={row}
                d={`M${spacing * 0.3} ${spacing * (row * 1.6 + 0.1)}l${-spacing * 0.13} ${spacing * 0.45} M${spacing * 0.8} ${spacing * (row * 1.6 + 0.85)}l${-spacing * 0.13} ${spacing * 0.45}`}
                stroke="#47788f"
                strokeWidth={Math.max(0.6, spacing * 0.035)}
                opacity="0.7"
              />
            ))}
          </g>
        </pattern>
      </defs>
      {paths.map((d) => (
        <path key={d.id} d={d.path} fill={`url(#${id})`} fillRule="evenodd" />
      ))}
    </g>
  );
}
