import type { CandidateMap } from '../entity/catalog';
import type { Cell, Placement } from '../../game/entity/game';
import { facilities, format } from '../../game/service/gameService';
import { positionPlanLabels } from '../service/planLabelService';

const points = (coordinates: [number, number][]) =>
  coordinates.map(([east, north]) => `${east},${-north}`).join(' ');

export function PlanMap({
  map,
  cells,
  placements,
  selectedCell,
  onCellSelect,
}: {
  map: CandidateMap;
  cells: Cell[];
  placements: Placement[];
  selectedCell: string | null;
  onCellSelect: (id: string) => void;
}) {
  const width = map.snapshot.widthM + 26;
  const height = map.snapshot.depthM + 26;
  const svg = useRef<SVGSVGElement>(null);
  const [scale, setScale] = useState(1);
  const labels = positionPlanLabels(
    cells.map((cell) => cell.center),
    scale,
    width,
    height
  );
  useLayoutEffect(() => {
    if (!svg.current) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0 && entry.contentRect.height > 0)
        setScale(Math.min(entry.contentRect.width / width, entry.contentRect.height / height));
    });
    observer.observe(svg.current);
    return () => observer.disconnect();
  }, [width, height]);
  return (
    <svg
      ref={svg}
      className="plan-map"
      viewBox={`${-width / 2} ${-height / 2} ${width} ${height}`}
      role="group"
      aria-label="시설 배치 2D 평면도"
    >
      <desc>
        같은 공개 경계와 실험 구역의 평면 표시. 구역을 Tab으로 찾아 Enter 또는 Space로 선택.
      </desc>
      <g aria-hidden="true">
        <rect x={-width / 2} y={-height / 2} width={width} height={height} fill="#e4e7d9" />
        {map.roads.map((road) => (
          <polyline
            key={road.id}
            points={points(road.coordinates)}
            fill="none"
            stroke="#c1c9bc"
            strokeWidth={
              ['primary', 'secondary'].includes(road.highway)
                ? 12
                : road.highway === 'footway'
                  ? 3.4
                  : 7
            }
          />
        ))}
        {map.buildings.map((building) => (
          <polygon
            key={building.id}
            points={points(building.coordinates)}
            fill="#f3f3e9"
            stroke="#a7b3a0"
            strokeWidth={0.6}
          />
        ))}
      </g>
      {cells.map((cell, index) => {
        const [labelEast, labelNorth] = labels[index];
        const placement = placements.find((p) => p.cellId === cell.id);
        const coverage = placement ? Math.sqrt(placement.areaM2 / cell.areaM2) : 0;
        const label = `${cell.id} · ${cell.name} · ${placement ? `${facilities[placement.facilityType].name} ${format.format(placement.areaM2)} m² 배치` : '미배치'}`;
        return (
          <g
            key={cell.id}
            role="button"
            tabIndex={0}
            aria-label={label}
            aria-pressed={selectedCell === cell.id}
            className={`plan-cell${selectedCell === cell.id ? ' selected' : ''}`}
            onClick={() => onCellSelect(cell.id)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onCellSelect(cell.id);
              }
            }}
          >
            <title>{label}</title>
            <polygon className="plan-surface" points={points(cell.coordinates)} />
            {placement && (
              <polygon
                points={points(
                  cell.coordinates.map(([east, north]) => [
                    cell.center[0] + (east - cell.center[0]) * coverage,
                    cell.center[1] + (north - cell.center[1]) * coverage,
                  ])
                )}
                fill={facilities[placement.facilityType].color}
              />
            )}
            {(labelEast !== cell.center[0] || labelNorth !== cell.center[1]) && (
              <line
                x1={cell.center[0]}
                y1={-cell.center[1]}
                x2={labelEast}
                y2={-labelNorth}
                stroke="#355d42"
                strokeWidth={1 / scale}
              />
            )}
            <rect
              className="plan-cell-label"
              x={labelEast - 16 / scale}
              y={-labelNorth - 12 / scale}
              width={32 / scale}
              height={24 / scale}
              rx={3 / scale}
            />
            <text
              x={labelEast}
              y={-labelNorth}
              textAnchor="middle"
              dominantBaseline="central"
              style={{ fontSize: 11 / scale }}
            >
              {placement ? '✓' : ''}
              {cell.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
import { useLayoutEffect, useRef, useState } from 'react';
