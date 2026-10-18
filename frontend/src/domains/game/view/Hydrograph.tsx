import { useState } from 'react';
import type { Job, Rainfall, SimulationResult } from '../entity/game';
import { format } from '../service/gameService';
export function Hydrograph({
  job,
  result,
  rainfall,
  designLabel = '내 설계',
}: {
  job?: Job | null;
  result?: SimulationResult | null;
  rainfall: Rainfall;
  designLabel?: string;
}) {
  const [minute, setMinute] = useState(0);
  const r = result ?? job?.result;
  if (!r) return null;
  const values = r.strategy.seriesM3s;
  const base = r.baseline.seriesM3s;
  if (!values.length || !base.length) return null;
  const max = Math.max(...values, ...(base ?? []), 0.001);
  const last = Math.max(values.length - 1, 1);
  const path = (arr: number[]) =>
    arr
      .map(
        (n, i) =>
          `${i ? 'L' : 'M'}${(i / Math.max(arr.length - 1, 1)) * 860},${100 - (n / max) * 85}`
      )
      .join(' ');
  const selectedMinute = Math.min(minute, values.length - 1);
  const labelTime = (index: number) =>
    new Date(
      new Date(rainfall.start).getTime() + (index + 1) * rainfall.intervalSeconds * 1000
    ).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
      hour12: false,
    });
  const time = labelTime(selectedMinute);
  return (
    <section className="hydrograph" aria-label="시설 전후 계산 유량">
      <div className="chart-heading">
        <div>
          <b>유출 흐름 비교</b>
          <span>같은 시각의 표면 단위 유량 합 · m³/s</span>
        </div>
        <div className="chart-key">
          <span>
            <i className="baseline" />
            시설 없음
          </span>
          <span>
            <i />
            {designLabel}
          </span>
        </div>
      </div>
      <svg
        viewBox="0 0 860 115"
        preserveAspectRatio="none"
        role="img"
        aria-label="시설 전후 유출량 비교 선 그래프"
      >
        <path d="M0 100H860 M0 55H860 M0 12H860" className="chart-grid" />
        <path d={path(base)} className="chart-base" />
        <path d={path(values)} className="chart-design" />
        <path d={`M${(selectedMinute / last) * 860} 8V100`} className="chart-cursor" />
      </svg>
      <div className="chart-time">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <span key={f}>{labelTime(Math.round(f * (values.length - 1)))}</span>
        ))}
      </div>
      <label className="chart-scrub">
        <span>
          {time} KST <b>{format.format(values[selectedMinute])} m³/s</b>
        </span>
        <input
          aria-label="계산 시각 탐색"
          type="range"
          min="0"
          max={values.length - 1}
          value={selectedMinute}
          onChange={(e) => setMinute(Number(e.target.value))}
        />
      </label>
    </section>
  );
}
