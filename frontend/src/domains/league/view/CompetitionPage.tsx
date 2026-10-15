import { useState, useEffect } from 'react';
import type { Account } from '../../account/entity/account';
import type { Lab } from '../../game/entity/game';
import type { League } from '../entity/league';
import { Leaderboard } from '../../game/view/Leaderboard';
import { LeaguePage } from './LeaguePage';
export function CompetitionPage({
  account,
  lab,
  onDesign,
  initialLeague = false,
}: {
  account: Account | null;
  lab: Lab;
  onDesign: (l: League) => void;
  initialLeague?: boolean;
}) {
  const [mode, setMode] = useState(initialLeague ? 'leagues' : 'general');
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [mode]);
  return (
    <>
      <div className="competition-switch" role="group" aria-label="기록 경쟁 유형">
        <button
          className={mode === 'general' ? 'active' : ''}
          aria-pressed={mode === 'general'}
          onClick={() => setMode('general')}
        >
          일반 탐색 기록
        </button>
        <button
          className={mode === 'leagues' ? 'active' : ''}
          aria-pressed={mode === 'leagues'}
          onClick={() => setMode('leagues')}
        >
          기관 리그
        </button>
      </div>
      {mode === 'general' ? (
        <Leaderboard />
      ) : (
        <LeaguePage key={account?.id ?? 'guest'} account={account} lab={lab} onDesign={onDesign} />
      )}
    </>
  );
}
