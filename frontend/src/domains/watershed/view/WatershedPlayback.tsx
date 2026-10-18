import { useId, useMemo, useState } from 'react';
import type { PlaybackCatalog, PlaybackFrame } from '../dto/playbackDto';
import type { WatershedLayout } from '../dto/watershedLayoutDto';
import { useWatershedPlayback } from '../controller/useWatershedPlayback';
import { layoutExtent } from '../service/watershedLayout';
import { playbackDepthColor, recordedFlowPoints } from '../service/playback';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';

export const playbackClock = (seconds: number) => {
  const h = Math.floor(seconds / 3600),
    m = Math.floor((seconds % 3600) / 60),
    s = seconds % 60;
  return `${h}시간 ${m}분 ${s.toLocaleString('ko-KR', { maximumFractionDigits: 3 })}초`;
};
export function WatershedPlaybackView({
  layout,
  catalog,
  frame,
  index,
  playing,
  onIndex,
  onPlaying,
}: {
  layout: WatershedLayout;
  catalog: PlaybackCatalog;
  frame: PlaybackFrame | null;
  index: number;
  playing: boolean;
  onIndex: (index: number) => void;
  onPlaying: (value: boolean) => void;
}) {
  const marker = useId().replace(/:/g, '');
  const [view, setView] = useState<'baseline' | 'strategy'>('strategy');
  const [selected, setSelected] = useState('');
  const extent = useMemo(
    () =>
      layoutExtent([
        ...layout.catchments.flatMap((c) => c.points),
        ...layout.nodes.map((n) => n.coordinate),
      ]),
    [layout]
  );
  const unit = Math.max(extent.width, extent.height) / 380;
  const values = frame?.cases.find((c) => c.id === view);
  const nodes = new Map(values?.state.nodes.map((n) => [n.id, n]) ?? []);
  const links = new Map(values?.state.links.map((n) => [n.id, n]) ?? []);
  const allNodes = [
    ...new Set(frame?.cases.flatMap((c) => c.state.nodes.map((n) => n.id)) ?? []),
  ].sort();
  const allLinks = [
    ...new Set(frame?.cases.flatMap((c) => c.state.links.map((n) => n.id)) ?? []),
  ].sort();
  const selectedId = selected || (allNodes.length ? 'n:' + allNodes[0] : '');
  const [kind, id] = [selectedId.slice(0, 1), selectedId.slice(2)];
  const requested = catalog.timesSeconds[index];
  const selectedFields =
    kind === 'n'
      ? [
          ['headM', '수두 · 원 기준고', 'm'],
          ['depthM', '절점 내부 수심', 'm'],
          ['storageM3', '저류량', 'm³'],
          ['overflowM3s', '월류 유량', 'm³/s'],
        ]
      : [
          ['flowM3s', '부호 있는 유량', 'm³/s'],
          ['depthM', '관로 내부 수심', 'm'],
          ['setting', '설정 비율', ''],
        ];
  const selectedRows = frame?.cases.map((c) => ({
    id: c.id,
    value: (kind === 'n' ? c.state.nodes : c.state.links).find((n) => n.id === id),
  }));
  return (
    <div className="watershed-playback" aria-label="관망 수위·유량 재생">
      <div className="watershed-layout-toolbar" role="group" aria-label="재생 설계 선택">
        {(['baseline', 'strategy'] as const).map((v) => (
          <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
            {v === 'baseline' ? '설치 전' : '설치 후'}
          </button>
        ))}
      </div>
      <p>
        <strong>계산 시작 후 {playbackClock(requested)}</strong>
      </p>
      <div className="watershed-playback-time">
        <button
          type="button"
          aria-label={playing ? '관망 재생 정지' : '관망 재생 시작'}
          disabled={!frame || index === catalog.timesSeconds.length - 1}
          onClick={() => onPlaying(!playing)}
        >
          {playing ? '정지' : '재생'}
        </button>
        <input
          aria-label="관망 재생 시각"
          type="range"
          min={0}
          max={catalog.timesSeconds.length - 1}
          step={1}
          value={index}
          onChange={(e) => {
            onPlaying(false);
            onIndex(Number(e.target.value));
          }}
        />
        <span>
          {index + 1}/{catalog.timesSeconds.length}
        </span>
      </div>
      {!frame ? (
        <p role="status">선택 시각의 원 계산 기록 조회 중…</p>
      ) : (
        <>
          <div className="watershed-playback-stamps">
            {frame.cases.map((c) => (
              <p key={c.id}>
                {c.id === 'baseline' ? '설치 전' : '설치 후'} 기록:{' '}
                {playbackClock(c.state.timeSeconds)} · 요청보다 {number(c.ageSeconds)}초 전
                {c.numericalStatus === 'FAILED' && (
                  <strong className="watershed-warning"> · 수치 실패 진단</strong>
                )}
              </p>
            ))}
          </div>
          <svg
            viewBox={`${extent.x} ${extent.y} ${extent.width} ${extent.height}`}
            role="group"
            aria-label="계산 수위와 유량 방향 관망도"
          >
            <defs>
              <marker
                id={marker}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M0,0 L10,5 L0,10 Z" fill="#17618a" />
              </marker>
            </defs>
            <g className="watershed-flood-context" aria-hidden="true">
              {layout.catchments.map((c) => (
                <polygon
                  key={c.id}
                  points={c.points.map(([x, y]) => `${x},${-y}`).join(' ')}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
            </g>
            {layout.links.map((l) => {
              const value = links.get(l.id);
              return (
                <polyline
                  key={l.id}
                  points={recordedFlowPoints(l.points, value?.flowM3s ?? 0)
                    .map(([x, y]) => `${x},${-y}`)
                    .join(' ')}
                  className="watershed-playback-link"
                  data-selected={selectedId === 'l:' + l.id}
                  vectorEffect="non-scaling-stroke"
                  markerEnd={value && value.flowM3s !== 0 ? `url(#${marker})` : undefined}
                  role="button"
                  tabIndex={0}
                  aria-label={`관로 ${l.id} 유량 ${value ? number(value.flowM3s) : '미확보'} m³/s`}
                  aria-pressed={selectedId === 'l:' + l.id}
                  onClick={() => setSelected('l:' + l.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelected('l:' + l.id);
                    }
                  }}
                >
                  <title>
                    {l.id} · 정의 방향 {l.fromNode} → {l.toNode} ·{' '}
                    {value ? number(value.flowM3s) + ' m³/s' : '기록 없음'}
                  </title>
                </polyline>
              );
            })}
            {layout.nodes.map((n) => {
              const value = nodes.get(n.id);
              return (
                <circle
                  key={n.id}
                  cx={n.coordinate[0]}
                  cy={-n.coordinate[1]}
                  r={unit * (selectedId === 'n:' + n.id ? 6 : 4)}
                  className="watershed-playback-node"
                  data-selected={selectedId === 'n:' + n.id}
                  data-overflow={value && value.overflowM3s > 0}
                  fill={value ? playbackDepthColor(value.depthM, catalog.depthScaleM) : '#cbd5e1'}
                  vectorEffect="non-scaling-stroke"
                  role="button"
                  tabIndex={0}
                  aria-label={`절점 ${n.id} 수심 ${value ? number(value.depthM) : '미확보'} m`}
                  aria-pressed={selectedId === 'n:' + n.id}
                  onClick={() => setSelected('n:' + n.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelected('n:' + n.id);
                    }
                  }}
                >
                  <title>
                    {n.id} · {value ? number(value.depthM) + ' m' : '기록 없음'}
                  </title>
                </circle>
              );
            })}
          </svg>
          <small>
            색상: 절점 내부 수심 0–{number(catalog.depthScaleM)} m · 두 안의 전체 기록에 같은 척도
            <br />
            화살표: 기록 유량 방향 · 주황 테두리: 해당 기록에서 월류 발생
          </small>
          <label className="watershed-flood-selection">
            상세 지점·관로
            <select
              aria-label="재생 상세 대상"
              value={selectedId}
              onChange={(e) => setSelected(e.target.value)}
            >
              <optgroup label="지점">
                {allNodes.map((n) => (
                  <option key={n} value={'n:' + n}>
                    {n}
                    {layout.nodes.some((v) => v.id === n) ? '' : ' · 좌표 없음'}
                  </option>
                ))}
              </optgroup>
              <optgroup label="관로·펌프">
                {allLinks.map((n) => (
                  <option key={n} value={'l:' + n}>
                    {n}
                    {layout.links.some((v) => v.id === n) ? '' : ' · 좌표 없음'}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          <div className="watershed-playback-table">
            <table>
              <caption>{id} · 같은 요청 시각의 기록 비교</caption>
              <thead>
                <tr>
                  <th>항목</th>
                  <th>설치 전</th>
                  <th>설치 후</th>
                </tr>
              </thead>
              <tbody>
                {selectedFields.map(([field, label, units]) => (
                  <tr key={field}>
                    <th>{label}</th>
                    {(['baseline', 'strategy'] as const).map((c) => {
                      const row = selectedRows?.find((r) => r.id === c)?.value;
                      const value =
                        row && field in row
                          ? (row as unknown as Record<string, number>)[field]
                          : null;
                      return (
                        <td key={c}>
                          {value == null ? '해당 시설 없음' : `${number(value)} ${units}`}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p>
        기록 사이를 보간하지 않습니다. 재생 수심은 관망 내부 값이며 지표 침수 깊이가 아닙니다.
        첨두·물수지는 별도 내부 단계 계산 결과를 사용합니다.
      </p>
      <details>
        <summary>재생 원본·표시 범위</summary>
        <p>
          원 연구 입력의 상대 시각과 원본 좌표입니다. 실제 서울 위치·재난 당시 관망의 복원 여부와
          구분합니다. 좌표 없는 설계는 상세 목록에서 확인할 수 있습니다.
        </p>
        {catalog.sources.map((s) => (
          <p key={s.id}>
            {s.id === 'baseline' ? '설치 전' : '설치 후'} 원 프레임 <code>{s.framesSha256}</code>
          </p>
        ))}
      </details>
    </div>
  );
}

function LoadedPlayback({ jobId, layout }: { jobId: string; layout: WatershedLayout }) {
  const state = useWatershedPlayback(jobId);
  return (
    <>
      {state.error ? (
        <p role="alert" className="watershed-warning">
          {state.error} <button onClick={state.retry}>다시 조회</button>
        </p>
      ) : state.catalog ? (
        <WatershedPlaybackView
          layout={layout}
          catalog={state.catalog}
          frame={state.frame}
          index={state.index}
          playing={state.playing}
          onIndex={state.setIndex}
          onPlaying={state.setPlaying}
        />
      ) : (
        <p role="status">관망 재생 목록 조회 중…</p>
      )}
    </>
  );
}
export function WatershedPlayback({ jobId, layout }: { jobId: string; layout: WatershedLayout }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="watershed-playback-section">
      <button className="watershed-submit" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? '수위·유량 재생 닫기' : '수위·유량 재생'}
      </button>
      {open && <LoadedPlayback key={jobId} jobId={jobId} layout={layout} />}
    </section>
  );
}
