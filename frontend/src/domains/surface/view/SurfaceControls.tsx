import type { SurfaceMetric } from '../entity/surface';
import type { useSurfacePlayback } from '../controller/useSurfacePlayback';
import { surfacePalette } from '../service/surfaceService';
import './surface.css';
export function SurfaceControls({
  enabled,
  onEnabled,
  metric,
  onMetric,
  state,
  hasSource,
  onSeek,
  renderError,
  live = false,
}: {
  enabled: boolean;
  onEnabled: (v: boolean) => void;
  metric: SurfaceMetric;
  onMetric: (v: SurfaceMetric) => void;
  state: ReturnType<typeof useSurfacePlayback>;
  hasSource: boolean;
  onSeek: (index: number) => void;
  renderError: boolean;
  live?: boolean;
}) {
  const { catalog, frame, loading, error, retry } = state;
  const time =
    frame && catalog ? new Date(Date.parse(catalog.startUtc) + frame.timeSeconds * 1000) : null;
  return (
    <div className="surface-controls">
      <label>
        <input type="checkbox" checked={enabled} onChange={(e) => onEnabled(e.target.checked)} />
        {live ? '현재 침수 계산' : '계산 침수'}
      </label>
      {enabled && (
        <>
          {!hasSource ? (
            <span>
              {live ? '현재 지도에 연결된 침수 계산 결과 없음' : '완료한 재해 실행을 선택하세요.'}
            </span>
          ) : error ? (
            <span role="alert">
              {error} <button onClick={retry}>다시 확인</button>
            </span>
          ) : !catalog ? (
            <span role="status">계산 결과 확인 중</span>
          ) : (
            <>
              <select
                aria-label="지표 계산 표시 값"
                value={metric}
                onChange={(e) => onMetric(e.target.value as SurfaceMetric)}
              >
                <option value="depth">수심 · m</option>
                <option value="speed">속력 · m/s</option>
              </select>
              <span className="surface-legend">
                {surfacePalette.map((color, i) => (
                  <span key={color}>
                    <i style={{ background: color }} />
                    {['0–0.1', '0.1–0.3', '0.3–0.5', '0.5–1', '1–2', '2+'][i]}
                  </span>
                ))}
              </span>
              <small>
                {live
                  ? '최근 5분 이내 계산값 · 관측 침수와 구분'
                  : '계산값 · 현장 검증 전 · 지표면 색상 표시'}
              </small>
              {!live && (
                <input
                  type="range"
                  aria-label="지표 계산 기록 시각"
                  min={0}
                  max={catalog.timesSeconds.length - 1}
                  value={state.index ?? 0}
                  onChange={(e) => onSeek(Number(e.target.value))}
                />
              )}
              {loading ? (
                <span role="status">불러오는 중</span>
              ) : time ? (
                <time dateTime={time.toISOString()}>
                  {time.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })} KST
                  · {frame!.cells.length.toLocaleString()}격자
                </time>
              ) : (
                <small>
                  {live
                    ? '최근 5분 이내 지표 계산 없음 · 과거 결과 표시 중지'
                    : '선택 시각의 지표 계산 없음'}
                </small>
              )}
              <details>
                <summary>계산 범위·출처</summary>
                <div className="surface-description">
                  {catalog.limitations.map((text, i) => (
                    <p key={i}>{text}</p>
                  ))}
                  <p>원 계산 해시 {catalog.surfaceResultSha256}</p>
                  <p>표시 프레임으로 점수·첨두를 다시 계산하지 않습니다.</p>
                </div>
              </details>
            </>
          )}
          {renderError && <span role="alert">3D 표시 실패 · 2D에서 확인 가능</span>}
        </>
      )}
    </div>
  );
}
