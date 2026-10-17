import { useId, useMemo } from 'react';
import type { City } from '../../city/entity/city';
import { polygonPath } from '../../catalog/service/mapGeometryService';
import { rainVisualDensity } from '../service/rainEffectService';

export function LiveRainPlan({
  districts,
  amounts,
  scale,
  animate,
}: {
  districts: City['districts'];
  amounts: ReadonlyMap<string, number | null>;
  scale: number;
  animate: boolean;
}) {
  const id = useId().replace(/:/g, '');
  const paths = useMemo(
    () => districts.map((d) => ({ id: d.id, path: polygonPath(d.polygons) })),
    [districts]
  );
  return (
    <g pointerEvents="none" aria-hidden="true">
      <defs>
        {paths.map((d) => {
          const density = rainVisualDensity(amounts.get(d.id));
          const spacing = Math.max(6, (scale * 0.016) / Math.sqrt(density));
          return (
            <pattern
              key={d.id}
              id={`${id}-${d.id}`}
              width={spacing}
              height={spacing * 1.6}
              patternUnits="userSpaceOnUse"
            >
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
                    opacity={Math.min(0.8, 0.35 + density * 0.25)}
                  />
                ))}
              </g>
            </pattern>
          );
        })}
      </defs>
      {paths.map((d) => (
        <path key={d.id} d={d.path} fill={`url(#${id}-${d.id})`} fillRule="evenodd" />
      ))}
    </g>
  );
}
