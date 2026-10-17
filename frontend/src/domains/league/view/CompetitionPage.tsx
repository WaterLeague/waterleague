import { useState, useEffect } from 'react';
import type { Account } from '../../account/entity/account';
import type { Lab, Version, RainfallCatalog } from '../../game/entity/game';
import type { League } from '../entity/league';
import { Leaderboard } from '../../game/view/Leaderboard';
import { LeaguePage } from './LeaguePage';
import { ComparisonPage } from '../../comparison/view/ComparisonPage';
export function CompetitionPage({
  account,
  lab,
  onDesign,
  initialLeague = false,
  version,
  catalog,
  onOpen,
  onStudio,
}: {
  account: Account | null;
  lab: Lab;
  onDesign: (l: League) => void;
  initialLeague?: boolean;
  version: Version | null;
  catalog: RainfallCatalog | null;
  onOpen: (id: string) => void;
  onStudio: () => void;
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
        <button
          className={mode === 'comparison' ? 'active' : ''}
          aria-pressed={mode === 'comparison'}
          onClick={() => setMode('comparison')}
        >
          내 강우 비교
        </button>
      </div>
      {mode === 'general' ? (
        <Leaderboard key={lab.modelHash} lab={lab} />
      ) : mode === 'comparison' ? (
        catalog ? (
          <ComparisonPage
            key={account?.id ?? 'guest'}
            account={account}
            version={version}
            catalog={catalog}
            onOpen={onOpen}
            onStudio={onStudio}
          />
        ) : (
          <p className="full-page" role="status">
            강우 목록을 불러오는 중입니다.
          </p>
        )
      ) : (
        <LeaguePage key={account?.id ?? 'guest'} account={account} lab={lab} onDesign={onDesign} />
      )}
    </>
  );
}
