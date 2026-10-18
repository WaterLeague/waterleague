import { memo, useCallback, useMemo, useState } from 'react';
import { CloudRain, Pause, Play, RotateCcw } from 'lucide-react';
import type { Cell, Job, Lab, Placement, Version } from '../entity/game';
import type { StormReplayData } from '../entity/stormReplay';
import type { CandidateMap } from '../../catalog/entity/catalog';
import { MapViewport } from '../../catalog/view/MapViewport';
import { useReducedMotion } from '../../catalog/controller/useReducedMotion';
import { createStormReplay } from '../service/stormReplayService';
import { useStormReplay } from '../controller/useStormReplay';
import { GameDataError } from '../exception/GameDataError';
import { facilities, format } from '../service/gameService';
import './replay.css';

const clock = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour12: false,
  hour: '2-digit',
  minute: '2-digit',
});
const day = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium' });
const flow = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 4 });
const empty: Placement[] = [];
const ReplayMap = memo(function ReplayMap({
  map,
  cells,
  placements,
}: {
  map: CandidateMap;
  cells: Cell[];
  placements: Placement[];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const select = useCallback(
    (id: string | null) => {
      setSelected(cells.find((c) => c.id === id || c.buildingId === id)?.id ?? null);
    },
    [cells]
  );
  const placement = placements.find((p) => p.cellId === selected);
  return (
    <>
      <MapViewport
        map={map}
        cells={cells}
        placements={placements}
        selectedCell={selected}
        onSelect={select}
      />
      {selected && (
        <p className="replay-selection">
          {selected} ·{' '}
          {placement
            ? `${facilities[placement.facilityType].name} ${format.format(placement.areaM2)} m²`
            : '설치 시설 없음'}
        </p>
      )}
    </>
  );
});

function Timeline({ data, index }: { data: StormReplayData; index: number }) {
  const paths = useMemo(() => {
    const x = (i: number) => 10 + (i / (data.frames.length - 1)) * 980;
    const y = (n: number) => 91 - (n / Math.max(data.maxFlowM3s, 1e-9)) * 75;
    return {
      baseline: data.frames.map((f, i) => `${i ? 'L' : 'M'}${x(i)} ${y(f.baselineM3s)}`).join(' '),
      design: data.frames.map((f, i) => `${i ? 'L' : 'M'}${x(i)} ${y(f.designM3s)}`).join(' '),
    };
  }, [data]);
  const cursor = 10 + (index / (data.frames.length - 1)) * 980;
  return (
    <div className="replay-timeline">
      <div className="replay-chart-label">
        <span>
          보고시각 유량{' '}
          <small>최대 {flow.format(data.maxFlowM3s)} m³/s · 시설 없음 / 계산한 설계</small>
        </span>
      </div>
      <svg
        viewBox="0 0 1000 105"
        preserveAspectRatio="none"
        role="img"
        aria-label="선택한 시각의 시설 전후 계산 유량"
      >
        <path d="M10 16H990M10 54H990M10 91H990" className="replay-grid" />
        <path d={paths.baseline} className="replay-base-path" />
        <path d={paths.design} className="replay-design-path" />
        <path d={`M${cursor} 10V98`} className="replay-cursor" />
      </svg>
      <div className="replay-chart-time">
        {[0, 0.25, 0.5, 0.75, 1].map((part) => (
          <span key={part}>
            {clock.format(data.frames[Math.round(part * (data.frames.length - 1))].time)}
          </span>
        ))}
      </div>
    </div>
  );
}

function ReplayView({
  data,
  lab,
  evaluated,
  map,
}: {
  data: StormReplayData;
  lab: Lab;
  evaluated: Version;
  map: CandidateMap | null;
}) {
  const replay = useStormReplay(data);
  const frame = data.frames[replay.index];
  const [baseline, setBaseline] = useState(false),
    [rainVisible, setRainVisible] = useState(true);
  const reducedMotion = useReducedMotion();
  const difference = frame.baselineM3s - frame.designM3s;
  const drops = Math.ceil((frame.rainMm / Math.max(data.maxRainMm, 1e-9)) * 64);
  const validMap = map?.snapshot.id === (lab.model.mapId ?? 'seongsu-candidate-01');
  return (
    <section className="storm-replay" aria-label="계산 결과 시간 재생">
      <div className="replay-stage">
        <div className="replay-map">
          {map && validMap ? (
            <ReplayMap
              map={map}
              cells={lab.model.cells}
              placements={baseline ? empty : evaluated.placements}
            />
          ) : (
            <p className="empty-state">계산한 지역 지도를 불러오는 중입니다.</p>
          )}
          {rainVisible && !reducedMotion && drops > 0 && (
            <svg
              className={`replay-rain ${replay.playing ? 'running' : ''}`}
              viewBox="0 0 1000 600"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {Array.from({ length: drops }, (_, i) => (
                <line
                  key={i}
                  x1={(i * 137 + 29) % 1000}
                  x2={((i * 137 + 29) % 1000) - 8}
                  y1={(i * 73 + 17) % 560}
                  y2={((i * 73 + 17) % 560) + 25}
                  style={{ animationDelay: `${-(i % 9) / 10}s` }}
                />
              ))}
            </svg>
          )}
          <div className="replay-map-heading">
            <span>STORM REPLAY</span>
            <b>
              {lab.model.mapTitle ?? '성수'} ·{' '}
              {baseline ? '시설 없음' : `저장 버전 ${evaluated.revision}`}
            </b>
          </div>
          <div className="replay-map-switch" role="group" aria-label="재생 지도 배치 비교">
            <button aria-pressed={baseline} onClick={() => setBaseline(true)}>
              시설 없음
            </button>
            <button aria-pressed={!baseline} onClick={() => setBaseline(false)}>
              계산한 설계
            </button>
            <button
              className="replay-rain-toggle"
              aria-pressed={rainVisible}
              aria-label="설명용 빗줄기 표시"
              onClick={() => setRainVisible((v) => !v)}
            >
              <CloudRain size={17} />
            </button>
          </div>
        </div>
        <aside className="replay-live">
          <span className="replay-eyebrow">{day.format(frame.time)} · KST</span>
          <time dateTime={new Date(frame.time).toISOString()}>{clock.format(frame.time)}</time>
          <div className="replay-flow-values">
            <h3>이 시각의 유출</h3>
            <small>선정 표면 단위의 합 · m³/s</small>
            <span className="replay-base-value">
              <i />
              시설 없음 <b>{flow.format(frame.baselineM3s)}</b>
            </span>
            <span className="replay-design-value">
              <i />
              계산한 설계 <b>{flow.format(frame.designM3s)}</b>
            </span>
            <p>
              {flow.format(Math.abs(difference))}{' '}
              <small>m³/s {difference > 0 ? '감소' : difference < 0 ? '증가' : '차이'}</small>
            </p>
          </div>
          <p className="replay-live-note">
            1분 보고시각의 계산값입니다. 실제 관망 유량이나 분 평균값이 아닙니다.
          </p>
        </aside>
      </div>
      <p className="replay-map-note">빗줄기는 설명용 표시 · 침수 깊이·지표 물길 계산 아님</p>
      <div className="replay-controls">
        <button
          className="replay-toggle"
          onClick={replay.toggle}
          aria-label={replay.playing ? '시계열 일시정지' : '시계열 재생'}
        >
          {replay.playing ? <Pause size={19} /> : <Play size={19} />}{' '}
          {replay.playing ? '일시정지' : '재생'}
        </button>
        <button className="replay-reset" aria-label="재생 처음으로" onClick={() => replay.seek(0)}>
          <RotateCcw size={16} />
        </button>
        <input
          type="range"
          min={0}
          max={data.frames.length - 1}
          value={replay.index}
          onChange={(e) => replay.seek(Number(e.target.value))}
          aria-label="결과 재생 시각"
          aria-valuetext={`${clock.format(frame.time)} KST, 계산한 설계 유량 ${flow.format(frame.designM3s)} m³/s`}
        />
        <label>
          재생 속도
          <select
            aria-label="시계열 재생 속도"
            value={replay.speed}
            onChange={(e) => replay.setSpeed(Number(e.target.value))}
          >
            {[30, 60, 120].map((speed) => (
              <option key={speed} value={speed}>
                1초 = {speed}분
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="replay-jumps">
        <span>시각 바로가기</span>
        <button onClick={() => replay.seek(data.flowPeakIndex)}>기준 유출 최대</button>
        <small>실제 기록된 구간만 재생</small>
      </div>
      <Timeline data={data} index={replay.index} />
    </section>
  );
}

export function StormReplay({
  job,
  lab,
  evaluated,
  map,
}: {
  job: Job;
  lab: Lab;
  evaluated: Version | null;
  map: CandidateMap | null;
}) {
  const state = useMemo(() => {
    try {
      return { data: createStormReplay(job, lab, evaluated), error: '' };
    } catch {
      return { data: null, error: new GameDataError().message };
    }
  }, [job, lab, evaluated]);
  if (!state.data || !evaluated)
    return (
      <p className="round-stale" role="alert">
        {state.error}
      </p>
    );
  return <ReplayView key={job.id} data={state.data} lab={lab} evaluated={evaluated} map={map} />;
}
