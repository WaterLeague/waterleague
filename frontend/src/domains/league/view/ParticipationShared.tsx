import type { ParticipantEvent } from '../entity/participation';
import { leagueTime } from '../service/leagueService';
import { participantNames } from '../service/participationService';
export function ActionMessage({ error, notice }: { error: string; notice: string }) {
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error} 상태를 새로고침한 뒤 확인해 주세요.
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
    </>
  );
}
export function InvitationCode({ code, onClose }: { code: string; onClose: () => void }) {
  return (
    <div className="invitation-code" role="status">
      <strong>지금 표시된 코드를 보관하세요.</strong>
      <code>{code}</code>
      <p>이 화면을 닫으면 다시 조회할 수 없습니다. 필요한 경우 새 코드로 교체할 수 있습니다.</p>
      <button type="button" className="outline-button" onClick={onClose}>
        코드 표시 닫기
      </button>
    </div>
  );
}
export function ParticipantHistory({ events }: { events: ParticipantEvent[] }) {
  return events.length > 0 ? (
    <details className="participant-history">
      <summary>참가 변경 이력 {events.length}건</summary>
      <ol>
        {events.map((e) => (
          <li key={e.revision}>
            <b>{participantNames[e.state]}</b>
            <time dateTime={e.createdAt}>{leagueTime(e.createdAt)}</time>
            {e.reason && <p>{e.reason}</p>}
          </li>
        ))}
      </ol>
    </details>
  ) : null;
}
