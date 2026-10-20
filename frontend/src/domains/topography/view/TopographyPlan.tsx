import { memo, useMemo } from 'react';
import type { TopographyView } from '../entity/topography';
import { topographyStyle } from '../service/topographyStyleService';
export const TopographyPlan = memo(function TopographyPlan({
  value,
  distance,
}: {
  value: TopographyView;
  distance: number;
}) {
  const layers = value.index?.layers;
  const labels = useMemo(() => {
    if (distance > 3500) return [];
    const occupied = new Set<string>();
    return value.tiles
      .flatMap((tile) => tile.data.labels)
      .filter((label) => {
        const key = `${Math.round(label.point[0] / (distance * 0.1))}:${Math.round(label.point[1] / (distance * 0.025))}`;
        if (occupied.has(key)) return false;
        occupied.add(key);
        return true;
      });
  }, [value.tiles, distance]);
  if (!layers) return null;
  return (
    <g pointerEvents="none">
      {value.tiles.map((tile) => (
        <g key={tile.id}>
          {tile.data.plan.map((part) => (
            <g key={part.layer}>
              {part.areas && (
                <path
                  d={part.areas}
                  fill={topographyStyle(layers[part.layer]).color}
                  fillRule="evenodd"
                />
              )}
              {part.lines && (
                <path
                  d={part.lines}
                  fill="none"
                  stroke={topographyStyle(layers[part.layer]).color}
                  strokeWidth={0.7}
                  vectorEffect="non-scaling-stroke"
                  opacity={0.75}
                />
              )}
              {part.points && (
                <path
                  d={part.points}
                  fill={layers[part.layer].color}
                  stroke={layers[part.layer].color}
                  strokeWidth={1.6}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              <title>{layers[part.layer].name}</title>
            </g>
          ))}
        </g>
      ))}
      {labels.map((label, index) => (
        <text
          key={index}
          x={label.point[0]}
          y={-label.point[1]}
          fontSize={distance * 0.011}
          textAnchor="middle"
          fill="#334e49"
          stroke="#fafbf6"
          strokeWidth={distance * 0.003}
          paintOrder="stroke"
        >
          {label.text}
        </text>
      ))}
    </g>
  );
});
