import type { TraceCatalog, TraceEvent } from '../entity/floodTrace';
import './flood-trace.css';

export function FloodTraceControls({
  enabled,
  onEnabled,
  eventId,
  onEvent,
  fixedEvent,
  catalog,
  event,
  loading,
  error,
  renderError,
  retry,
}: {
  enabled: boolean;
  onEnabled: (value: boolean) => void;
  eventId: string;
  onEvent: (id: string) => void;
  fixedEvent: boolean;
  catalog: TraceCatalog | null;
  event: TraceEvent | undefined;
  loading: boolean;
  error: boolean;
  renderError: boolean;
  retry: () => void;
}) {
  return (
    <div className="flood-trace-controls">
      <label className="flood-trace-toggle">
        <input type="checkbox" checked={enabled} onChange={(e) => onEnabled(e.target.checked)} />
        <i aria-hidden="true" />
        침수흔적
      </label>
      {enabled && (
        <>
          {!fixedEvent && catalog ? (
            <select
              aria-label="참고할 침수흔적 사건"
              value={eventId}
              onChange={(e) => onEvent(e.target.value)}
            >
              {catalog.events.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.title}
                </option>
              ))}
            </select>
          ) : (
            event && <span>{event.title}</span>
          )}
          <small>사건 전체 기록 · 재생 시각 수심 아님</small>
          {event && (
            <details>
              <summary>자료 설명</summary>
              <div className="flood-trace-description">
                <b>
                  {event.periodStart} ~ {event.periodEnd}
                </b>
                <p>
                  침수 시작 날짜가 이 사건 기간에 해당하는 공개 기록{' '}
                  {event.includedCount.toLocaleString('ko-KR')}건의 범위입니다. 같은 장소의 중첩은
                  합쳐 표시합니다. 자료가 없는 곳을 침수가 없었던 곳으로 판단할 수는 없습니다.
                </p>
                <p>
                  종료 날짜 미확인{' '}
                  {(event.statusCounts.INCLUDED_WITHOUT_END_DATE ?? 0).toLocaleString('ko-KR')}건
                  포함. 유효하지 않은 도형 {event.statusCounts.INVALID_GEOMETRY ?? 0}건은 표시에서
                  제외했습니다.
                </p>
                <p>
                  계산 결과·현재 위험도와 별개이며 재생 시간에 따라 수심을 추정하지 않습니다. 파일
                  수정일 {event.fileModifiedAt} · 표시 형상 1mm 반올림은 조사 정확도가 아닙니다.
                </p>
                <a href={catalog?.sourceUrl} target="_blank" rel="noreferrer">
                  서울특별시 원본 · 공공누리 제1유형
                </a>
              </div>
            </details>
          )}
          {error ? (
            <span role="alert">
              자료 불러오기 실패 <button onClick={retry}>다시 시도</button>
            </span>
          ) : loading || !catalog ? (
            <span role="status">불러오는 중</span>
          ) : !event ? (
            <span role="status">이 사건의 확보 자료 없음</span>
          ) : null}
          {renderError && <span role="alert">3D 표시 실패 · 2D에서 확인 가능</span>}
        </>
      )}
    </div>
  );
}
