import { useState, useEffect } from 'react';
import type { Account } from '../../account/entity/account';
import { WeeklyBoard } from '../../weekly/view/WeeklyBoard';
import { useWeekly } from '../../weekly/controller/useWeekly';
import { HistoricalBoard } from '../../historical/view/HistoricalBoard';
export function CompetitionPage({
  account,
  initialLeague = false,
  onWeeklyDistrict,
  onLogin,
}: {
  account: Account | null;
  onLogin: () => void;
  onWeeklyDistrict: (id: string) => void;
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
          className={mode === 'historical' ? 'active' : ''}
          aria-pressed={mode === 'historical'}
          onClick={() => setMode('historical')}
        >
          재해 실험
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
      ) : mode === 'historical' ? (
        account ? (
          <HistoricalBoard key={account.id} />
        ) : (
          <section className="full-page historical-board">
            <h1>재해 실험 기록 경쟁</h1>
            <p>제출한 설계의 최종 점수와 순위는 로그인 후 확인할 수 있습니다.</p>
            <button className="solid-button" onClick={onLogin}>
              로그인하고 최종 기록 보기
            </button>
          </section>
        )
      ) : (
        <section className="full-page league-page" aria-label="기관 리그 준비 중">
          <h1>기관 리그</h1>
          <p className="lead">준비 중입니다.</p>
        </section>
      )}
    </>
  );
}
