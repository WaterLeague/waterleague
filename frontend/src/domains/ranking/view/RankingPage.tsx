import { useState, useEffect } from 'react';
import type { Account } from '../../account/entity/account';
import { WeeklyBoard } from '../../weekly/view/WeeklyBoard';
import { useWeekly } from '../../weekly/controller/useWeekly';
import { HistoricalBoard } from '../../historical/view/HistoricalBoard';
import { SitePageHeader } from '../../../shared/ui/SitePageHeader';
export function RankingPage({
  account,
  onWeeklyDistrict,
  onLogin,
}: {
  account: Account | null;
  onLogin: () => void;
  onWeeklyDistrict: (id: string) => void;
}) {
  const weekly = useWeekly(true, account?.id ?? null);
  const [mode, setMode] = useState('general');
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [mode]);
  return (
    <main className="site-page ranking-page">
      <SitePageHeader
        title="랭킹"
        description="주간 서울 대항전의 구별 기여와 재해 모드의 개인 기록을 확인하세요."
      />
      <div className="competition-switch" role="group" aria-label="랭킹 유형">
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
          재해 모드
        </button>
      </div>
      {mode === 'general' ? (
        <WeeklyBoard
          value={weekly.value}
          error={weekly.error}
          ownDistrictId={account?.districtId ?? null}
          onDistrict={onWeeklyDistrict}
        />
      ) : account ? (
        <HistoricalBoard key={account.id} />
      ) : (
        <section className="historical-board site-empty">
          <h2>재해 모드 랭킹</h2>
          <p>제출한 설계의 최종 점수와 순위는 로그인 후 확인할 수 있습니다.</p>
          <button className="solid-button" onClick={onLogin}>
            로그인하고 기록 보기
          </button>
        </section>
      )}
    </main>
  );
}
