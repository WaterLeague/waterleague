import type { WatershedMapSelection } from '../service/watershedMap';
import { polygonPath } from '../../catalog/service/mapGeometryService';
export function WatershedMapPlan({ map, selectedId, disabled, onSelect }: WatershedMapSelection) {
  return (
    <g aria-label="서초 연구 관망 · 도로 대조 위치 가정">
      {map.catchments.map((c) => (
        <path
          key={c.id}
          d={polygonPath([[c.points]])}
          fill={c.id === selectedId ? '#f2b43b' : '#2c879a'}
          fillOpacity={c.id === selectedId ? 0.28 : 0.1}
          stroke="#277888"
          strokeWidth={1.5}
          strokeDasharray="5 3"
          vectorEffect="non-scaling-stroke"
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-label={`연결 집수구역 ${c.id}`}
          aria-pressed={c.id === selectedId}
          aria-disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            if (!disabled) onSelect(c.id);
          }}
          onKeyDown={(event) => {
            if (!disabled && ['Enter', ' '].includes(event.key)) {
              event.preventDefault();
              event.stopPropagation();
              onSelect(c.id);
            }
          }}
        >
          <title>
            {c.id} · 배수 절점 {c.outletNodeId} · 연구 모형의 위치 가정
          </title>
        </path>
      ))}
      {map.links.map((l) => (
        <polyline
          key={l.id}
          points={l.points.map(([x, y]) => `${x},${-y}`).join(' ')}
          fill="none"
          stroke="#16435f"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          pointerEvents="none"
        />
      ))}
      {map.nodes.map((n) => (
        <circle
          key={n.id}
          cx={n.coordinate[0]}
          cy={-n.coordinate[1]}
          r={n.kind === 'OUTFALL' ? 7 : 3}
          fill={n.kind === 'OUTFALL' ? '#c3423f' : '#16435f'}
          pointerEvents="none"
        />
      ))}
    </g>
  );
}
