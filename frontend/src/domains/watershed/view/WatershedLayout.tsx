import { useId, useMemo, useState } from 'react';
import type { WatershedLayout as Layout } from '../dto/watershedLayoutDto';
import type { NetworkPlacement } from '../dto/watershedDto';
import { downstreamLayout, layoutExtent, layoutLabel } from '../service/watershedLayout';
export function WatershedLayout({
  layout,
  selectedId,
  placements,
  onSelect,
  disabled = false,
  selectedLinkId,
  selectableLinkIds,
  onSelectLink,
}: {
  layout: Layout;
  selectedId: string;
  placements: NetworkPlacement[];
  onSelect: (id: string) => void;
  disabled?: boolean;
  selectedLinkId?: string;
  selectableLinkIds?: string[];
  onSelectLink?: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(false);
  const marker = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const allExtent = useMemo(
    () =>
      layoutExtent([
        ...layout.catchments.flatMap((c) => c.points),
        ...layout.nodes.map((n) => n.coordinate),
      ]),
    [layout]
  );
  const labels = useMemo(
    () => new Map(layout.catchments.map((c) => [c.id, layoutLabel(c.points)])),
    [layout]
  );
  const selected = layout.catchments.find((c) => c.id === selectedId)!;
  const link = layout.links.find((l) => l.id === selectedLinkId);
  const extent =
    zoom && (link || selected) ? layoutExtent(link?.points ?? selected.points) : allExtent;
  const downstream = downstreamLayout(layout, selectedId);
  const unit = Math.max(extent.width, extent.height) / 370;
  return (
    <section className="watershed-layout" aria-label="공개 관망 구역 선택">
      <header>
        <strong>{onSelectLink ? '관로 연결을 눌러 설계' : '집수구역을 눌러 설계'}</strong>
        <span>원본 관망도</span>
      </header>
      <svg
        viewBox={`${extent.x} ${extent.y} ${extent.width} ${extent.height}`}
        role="group"
        aria-label="공개 집수구역과 배수 연결"
      >
        <defs>
          <marker
            id={marker}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="4"
            markerHeight="4"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#356e83" />
          </marker>
        </defs>
        {layout.catchments.map((c) => (
          <polygon
            key={c.id}
            points={c.points.map(([x, y]) => `${x},${-y}`).join(' ')}
            className="watershed-catchment"
            data-selected={c.id === selectedId}
            role="button"
            tabIndex={disabled || onSelectLink ? -1 : 0}
            aria-label={`${c.id} 집수구역 선택`}
            aria-pressed={c.id === selectedId}
            aria-disabled={disabled || Boolean(onSelectLink)}
            vectorEffect="non-scaling-stroke"
            onClick={() => {
              if (!disabled && !onSelectLink) onSelect(c.id);
            }}
            onKeyDown={(e) => {
              if (!disabled && !onSelectLink && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                onSelect(c.id);
              }
            }}
          >
            <title>
              {c.id} · 배수 절점 {c.outletNodeId}
            </title>
          </polygon>
        ))}
        <g className="watershed-connection-lines" aria-hidden="true">
          {layout.links.map((l) => (
            <polyline
              key={l.id}
              points={l.points.map(([x, y]) => `${x},${-y}`).join(' ')}
              data-selected={l.id === selectedLinkId || downstream.links.has(l.id)}
              vectorEffect="non-scaling-stroke"
              markerEnd={downstream.links.has(l.id) ? `url(#${marker})` : undefined}
            />
          ))}
          {layout.nodes.map((n) => (
            <circle
              key={n.id}
              cx={n.coordinate[0]}
              cy={-n.coordinate[1]}
              r={unit * (n.kind === 'OUTFALL' ? 4.5 : n.id === downstream.start ? 4 : 2)}
              data-outfall={n.kind === 'OUTFALL'}
              data-selected={
                downstream.nodes.has(n.id) || n.id === link?.fromNode || n.id === link?.toNode
              }
            />
          ))}
        </g>
        {onSelectLink && (
          <g className="watershed-link-targets">
            {layout.links
              .filter((l) => selectableLinkIds?.includes(l.id))
              .map((l) => (
                <polyline
                  key={l.id}
                  points={l.points.map(([x, y]) => `${x},${-y}`).join(' ')}
                  role="button"
                  tabIndex={disabled ? -1 : 0}
                  aria-disabled={disabled}
                  aria-label={`${l.id} 관로 연결 선택`}
                  aria-pressed={l.id === selectedLinkId}
                  vectorEffect="non-scaling-stroke"
                  onClick={() => {
                    if (!disabled) onSelectLink(l.id);
                  }}
                  onKeyDown={(e) => {
                    if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault();
                      onSelectLink(l.id);
                    }
                  }}
                >
                  <title>
                    {l.id} · {l.fromNode} → {l.toNode}
                  </title>
                </polyline>
              ))}
          </g>
        )}
        <g className="watershed-layout-labels" aria-hidden="true" fontSize={unit * 11}>
          {layout.catchments.map((c) => {
            const point = labels.get(c.id)!;
            const count = placements.filter((p) => p.catchmentId === c.id).length;
            return (
              <text
                key={c.id}
                x={point[0]}
                y={-point[1]}
                textAnchor="middle"
                dominantBaseline="central"
                fontWeight={c.id === selectedId ? 750 : 500}
              >
                <tspan>{c.id}</tspan>
                {count > 0 && (
                  <tspan x={point[0]} dy={unit * 12} fontSize={unit * 9}>
                    {count}곳
                  </tspan>
                )}
              </text>
            );
          })}
          {layout.nodes
            .filter((n) => n.kind === 'OUTFALL' || n.id === link?.fromNode || n.id === link?.toNode)
            .map((n) => (
              <text key={n.id} x={n.coordinate[0] + 7 * unit} y={-n.coordinate[1]}>
                {n.id}
              </text>
            ))}
        </g>
      </svg>
      <div className="watershed-layout-toolbar">
        <button type="button" aria-pressed={!zoom} onClick={() => setZoom(false)}>
          전체 관망
        </button>
        <button type="button" aria-pressed={zoom} onClick={() => setZoom(true)}>
          선택 구역 확대
        </button>
      </div>
      <p className="watershed-layout-route" aria-live="polite">
        {link
          ? `${link.id} · ${link.fromNode} → ${link.toNode}`
          : `${selectedId} → ${downstream.start} → 연결 방류구 ${downstream.outfalls.join('·') || '없음'}`}
      </p>
      <p>
        {onSelectLink
          ? '파란색: 저류조를 추가할 기존 관로의 연결점'
          : '노란색: 선택 구역 · 파란색: 하류 연결'}
        <br />
        화살표는 관로 정의 방향이며 실제 유량 방향이 아닙니다.
      </p>
      <details>
        <summary>원본 좌표·표시 범위</summary>
        {layout.limitations.map((s, i) => (
          <p key={i}>{s}</p>
        ))}
      </details>
    </section>
  );
}
