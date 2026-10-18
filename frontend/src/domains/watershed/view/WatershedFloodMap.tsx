import { useMemo, useState } from 'react';
import type { NodeFlooding } from '../dto/nodeFloodingDto';
import type { WatershedLayout } from '../dto/watershedLayoutDto';
import { compareNodeFlooding, floodNodeColor, type FloodView } from '../service/nodeFlooding';
import { layoutExtent } from '../service/watershedLayout';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';

export function WatershedFloodMap({
  layout,
  baseline,
  strategy,
}: {
  layout: WatershedLayout;
  baseline: NodeFlooding;
  strategy: NodeFlooding;
}) {
  const rows = useMemo(() => compareNodeFlooding(baseline, strategy), [baseline, strategy]);
  const [view, setView] = useState<FloodView>('change');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected =
    rows.find((n) => n.id === selectedId) ??
    rows.reduce((a, b) => (Math.abs(a.reductionM3) >= Math.abs(b.reductionM3) ? a : b));
  const extent = useMemo(
    () =>
      layoutExtent([
        ...layout.catchments.flatMap((c) => c.points),
        ...layout.nodes.map((n) => n.coordinate),
      ]),
    [layout]
  );
  const unit = Math.max(extent.width, extent.height) / 380;
  const absoluteMaximum = Math.max(...rows.flatMap((n) => [n.baselineM3, n.strategyM3]));
  const changeMaximum = Math.max(...rows.map((n) => Math.abs(n.reductionM3)));
  const maximum = view === 'change' ? changeMaximum : absoluteMaximum;
  const value = (n: typeof selected) =>
    view === 'change' ? n.reductionM3 : view === 'baseline' ? n.baselineM3 : n.strategyM3;
  const difference = (n: number) =>
    `${number(Math.abs(n))} m³ ${n > 0 ? '감소' : n < 0 ? '증가' : '변화 없음'}`;
  const unmapped = strategy.nodes.filter((n) => !n.mapped);
  return (
    <section className="watershed-flood-map" aria-label="지점별 월류 비교">
      <h3>어디에서 물이 넘쳤나</h3>
      <div className="watershed-layout-toolbar" role="group" aria-label="월류 표시 기준">
        {(
          [
            ['change', '설치 전후 변화'],
            ['baseline', '설치 전'],
            ['strategy', '설치 후'],
          ] as const
        ).map(([id, label]) => (
          <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
            {label}
          </button>
        ))}
      </div>
      <p className="watershed-flood-legend">
        {view === 'change'
          ? '녹색: 감소 · 주황: 증가 · 회색: 변화 없음'
          : '파란색: 월류 발생 · 회색: 월류 0 m³'}
      </p>
      <small>
        진한 색일수록 {view === 'change' ? '변화량' : '월류량'}이 큽니다. 색상 상한{' '}
        {number(maximum)} m³
        {view !== 'change' && ' · 설치 전후 같은 척도'}
      </small>
      <svg
        viewBox={`${extent.x} ${extent.y} ${extent.width} ${extent.height}`}
        role="group"
        aria-label="원본 관망 지점별 누적 월류"
      >
        <g className="watershed-flood-context" aria-hidden="true">
          {layout.catchments.map((c) => (
            <polygon
              key={c.id}
              points={c.points.map(([x, y]) => `${x},${-y}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {layout.links.map((l) => (
            <polyline
              key={l.id}
              points={l.points.map(([x, y]) => `${x},${-y}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>
        {rows.map((n) => {
          const p = layout.nodes.find((p) => p.id === n.id)!.coordinate;
          return (
            <g key={n.id}>
              <circle
                cx={p[0]}
                cy={-p[1]}
                r={unit * (n.id === selected.id ? 7 : 5)}
                fill={floodNodeColor(view, value(n), maximum)}
                className="watershed-flood-node"
                data-selected={n.id === selected.id}
                role="button"
                tabIndex={0}
                aria-pressed={n.id === selected.id}
                aria-label={`${n.id} · ${view === 'change' ? difference(n.reductionM3) : `${number(value(n))} m³`}`}
                onClick={() => setSelectedId(n.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedId(n.id);
                  }
                }}
                vectorEffect="non-scaling-stroke"
              >
                <title>
                  {n.id} · 설치 전 {number(n.baselineM3)} → 설치 후 {number(n.strategyM3)} m³
                </title>
              </circle>
              {(n.id === selected.id || n.kind === 'OUTFALL') && (
                <text
                  x={p[0] + unit * 8}
                  y={-p[1]}
                  dominantBaseline="central"
                  fontSize={unit * 10}
                  className="watershed-flood-label"
                  aria-hidden="true"
                >
                  {n.id}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <label className="watershed-flood-selection">
        지점 선택
        <select
          aria-label="지점 선택"
          value={selected.id}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {rows.map((n) => (
            <option key={n.id} value={n.id}>
              {n.id}
              {n.kind === 'OUTFALL' ? ' · 방류구' : ''}
            </option>
          ))}
        </select>
      </label>
      <div className="watershed-flood-detail" aria-live="polite">
        <strong>
          {selected.id} · {difference(selected.reductionM3)}
        </strong>
        <p>
          설치 전 {number(selected.baselineM3)} → 설치 후 {number(selected.strategyM3)} m³
        </p>
      </div>
      <p>
        계산 시작부터 {number(baseline.endSeconds)}초까지 누적한 월류량입니다. 지표 침수 깊이·침수
        구역을 뜻하지 않습니다.
      </p>
      <small>공개 연구 모형의 원본 좌표 · 서울 지도 위치 정합 전</small>
      {unmapped.length > 0 && (
        <details>
          <summary>좌표 없는 추가 설계 {unmapped.length}개</summary>
          {unmapped.map((n) => (
            <p key={n.id}>
              {n.id} · 월류 {number(n.floodingM3)} m³ · 지도 표시 제외
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
