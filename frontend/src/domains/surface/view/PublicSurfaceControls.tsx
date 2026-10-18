import type { SurfaceMetric } from '../entity/surface';
import type { usePublicSurfaces } from '../controller/usePublicSurfaces';
import { surfacePalette } from '../service/surfaceService';
import './surface.css';
export function PublicSurfaceControls({
  state,
  metric,
  onMetric,
  renderError,
}: {
  state: ReturnType<typeof usePublicSurfaces>;
  metric: SurfaceMetric;
  onMetric: (value: SurfaceMetric) => void;
  renderError: boolean;
}) {
  return (
    <div className="surface-controls" aria-label="현재 공개 유역 계산">
      <strong>지금의 물 흐름</strong>
      {state.error ? (
        <span role="alert">
          {state.error} <button onClick={state.retry}>다시 확인</button>
        </span>
      ) : state.loading ? (
        <span role="status">현재 계산 결과 확인 중</span>
      ) : !state.frames.length ? (
        <span>현재 지도에 연결된 침수 계산 결과 없음</span>
      ) : null}
      {!!state.frames.length && (
        <>
          <span>공개 기준안 · {state.frames.length}개 유역</span>
          <select
            aria-label="지표 계산 표시 값"
            value={metric}
            onChange={(e) => onMetric(e.target.value as SurfaceMetric)}
          >
            <option value="depth">수심 · m</option>
            <option value="speed">속력·흐름 방향 · m/s</option>
          </select>
          <span className="surface-legend">
            {surfacePalette.map((color, i) => (
              <span key={color}>
                <i style={{ background: color }} />
                {['0–0.1', '0.1–0.3', '0.3–0.5', '0.5–1', '1–2', '2+'][i]}
              </span>
            ))}
          </span>
          {metric === 'speed' && (
            <small>색상: 속력 · 화살표: 흐름 방향 · 방향 자료가 있는 격자만 표시</small>
          )}
          <small>최근 5분 이내 계산값 · 과거 침수 기록과 구분 · 현장 검증 전</small>
          <details>
            <summary>계산 범위·출처</summary>
            <div className="surface-description">
              {state.current?.runs.map((run) => (
                <section key={run.id}>
                  <strong>{run.name}</strong>
                  <p>
                    계산 시각{' '}
                    {new Date(run.lastFrameAt).toLocaleString('ko-KR', {
                      timeZone: 'Asia/Seoul',
                      hour12: false,
                    })}{' '}
                    KST
                  </p>
                  {run.catalog.limitations.map((text, i) => (
                    <p key={i}>{text}</p>
                  ))}
                  <p>원 계산 해시 {run.catalog.surfaceResultSha256}</p>
                  <p>공개 입력 묶음 {run.inputBundleSha256}</p>
                </section>
              ))}
              <p>
                회원 설계·점수와 분리된 공개 기준안입니다. 유역 결과를 합산하거나 미확보 영역을
                채우지 않습니다.
              </p>
            </div>
          </details>
        </>
      )}
      {renderError && <span role="alert">3D 표시 실패 · 2D에서 확인 가능</span>}
    </div>
  );
}
