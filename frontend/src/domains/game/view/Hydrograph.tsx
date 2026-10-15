import { useState } from 'react';
import type { Job, Rainfall } from '../entity/game';
import { rainDate } from './RainfallSelector';
import { format } from '../service/gameService';
export function Hydrograph({ job, rainfall }: { job: Job | null; rainfall: Rainfall }) {
  const [minute, setMinute] = useState(0);
  const r = job?.result;
  const values = r?.strategy.seriesM3s ?? rainfall.depthsMm;
  const base = r?.baseline.seriesM3s;
  const max = Math.max(...values, ...(base ?? []), 0.001);
  const path = (arr: number[]) =>
    arr
      .map((n, i) => `${i ? 'L' : 'M'}${(i / (arr.length - 1)) * 860},${100 - (n / max) * 85}`)
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
    <section className="hydrograph" aria-label="관측 강우와 계산 시계열">
      <div className="chart-heading">
        <div>
          <b>{r ? '유출 흐름 비교' : '기상청 실제 관측 강우'}</b>
          <span>
            {r
              ? '같은 시각의 표면 단위 유량 합 · m³/s'
              : `분당 깊이 · mm · ${rainDate(rainfall.start)}`}
          </span>
        </div>
        <div className="chart-key">
          {r && (
            <span>
              <i className="baseline" />
              시설 없음
            </span>
          )}
          <span>
            <i />
            {r ? '내 설계' : '관측 강우'}
          </span>
        </div>
      </div>
      <svg
        viewBox="0 0 860 115"
        preserveAspectRatio="none"
        role="img"
        aria-label={r ? '시설 전후 유출량 비교 선 그래프' : '실측 분당 강우 그래프'}
      >
        <path d="M0 100H860 M0 55H860 M0 12H860" className="chart-grid" />
        {base && <path d={path(base)} className="chart-base" />}
        <path d={path(values)} className="chart-design" />
        <path
          d={`M${(selectedMinute / (values.length - 1)) * 860} 8V100`}
          className="chart-cursor"
        />
      </svg>
      <div className="chart-time">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <span key={f}>{labelTime(Math.round(f * (values.length - 1)))}</span>
        ))}
      </div>
      <label className="chart-scrub">
        <span>
          {time} KST{' '}
          <b>
            {format.format(values[Math.min(minute, values.length - 1)] ?? 0)} {r ? 'm³/s' : 'mm'}
          </b>
        </span>
        <input
          aria-label="관측 시각 탐색"
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
