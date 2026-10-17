import { useState, useEffect, type ReactNode } from 'react';
import type { Account } from '../../account/entity/account';
import type { Lab } from '../../game/entity/game';
import type { League } from '../entity/league';
import { WeeklyBoard } from '../../weekly/view/WeeklyBoard';
import { useWeekly } from '../../weekly/controller/useWeekly';
import { LeaguePage } from './LeaguePage';
export function CompetitionPage({
  account,
  lab,
  onDesign,
  initialLeague = false,
  onWeeklyDistrict,
  submittedConditions,
}: {
  account: Account | null;
  lab: Lab;
  onDesign: (l: League) => void;
  onWeeklyDistrict: (id: string) => void;
  submittedConditions: ReactNode;
  initialLeague?: boolean;
}) {
  const weekly = useWeekly(true, account?.id ?? null);
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
          주간 서울 대항전
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
        <WeeklyBoard
          value={weekly.value}
          error={weekly.error}
          ownDistrictId={account?.districtId ?? null}
          onDistrict={onWeeklyDistrict}
        />
      ) : (
        <>
          {submittedConditions}
          <LeaguePage
            key={account?.id ?? 'guest'}
            account={account}
            lab={lab}
            onDesign={onDesign}
          />
        </>
      )}
    </>
  );
}
