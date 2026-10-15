import { useRef, useState } from 'react';
import type { League } from '../entity/league';
import * as repo from '../repository/participationRepository';
import { useLeagueAction } from '../controller/useLeagueAction';
import { validInvitation } from '../service/participationService';
import { LeagueRulesPanel } from './LeagueRulesPanel';
import { ActionMessage } from './ParticipationShared';
export function LeagueInviteForm({ onJoined }: { onJoined: (id: string) => void }) {
  const [code, setCode] = useState(''),
    [preview, setPreview] = useState<League | null>(null),
    [accepted, setAccepted] = useState(false);
  const generation = useRef(0),
    action = useLeagueAction();
  const clear = () => {
    generation.current++;
    setCode('');
    setPreview(null);
    setAccepted(false);
  };
  return (
    <section className="league-invite-entry">
      <h2>초대받은 리그</h2>
      <p>주최자가 전달한 리그 코드를 입력하고 참가 규칙을 확인하세요.</p>
      <form
        className="invitation-input"
        onSubmit={async (e) => {
          e.preventDefault();
          const revision = generation.current;
          const l = await action.run(() => repo.previewInvitation(code.trim()));
          if (l && revision === generation.current) {
            setPreview(l);
            setAccepted(false);
          }
        }}
      >
        <label>
          리그 초대 코드
          <input
            value={code}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={43}
            onChange={(e) => {
              generation.current++;
              setCode(e.target.value);
              setPreview(null);
              setAccepted(false);
            }}
          />
        </label>
        <button className="outline-button" disabled={action.busy || !validInvitation(code.trim())}>
          리그 규칙 확인
        </button>
      </form>
      <ActionMessage {...action} />
      {preview && (
        <div className="invitation-preview">
          <LeagueRulesPanel league={preview} />
          <label className="league-check">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            고정 규칙과 참가 방식 확인. 연구 공유는 별도 동의
          </label>
          <div className="league-actions">
            <button
              className="primary-button"
              disabled={action.busy || !accepted}
              onClick={async () => {
                const id = preview.id,
                  revision = generation.current;
                const ok = await action.run(async () => {
                  await repo.join(id, preview.rulesHash, code.trim());
                  return true;
                });
                if (ok && revision === generation.current) {
                  clear();
                  onJoined(id);
                }
              }}
            >
              {preview.rules.participation?.admission === 'APPROVAL'
                ? '참가 승인 신청'
                : '이 리그에 참가'}
            </button>
            <button className="outline-button" disabled={action.busy} onClick={clear}>
              미리보기 닫기
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
