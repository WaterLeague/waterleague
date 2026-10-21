import { useEffect, useState } from 'react';
import { ArrowUpRight, LogOut, X } from 'lucide-react';
import { useAccountSession } from '../../account/controller/useAccountSession';
import { memberTypeNames } from '../../account/entity/account';
import { AuthDialog } from '../../account/view/AuthDialog';
import { ApprovalPage } from '../../administration/view/ApprovalPage';
import { RankingPage } from '../../ranking/view/RankingPage';
import { CompetitionPage } from '../../competition/view/CompetitionPage';
import { ResultsPage } from '../../administration/view/ResultsPage';
import { useAppLocation, navigate, followLink } from '../../../shared/controller/useAppLocation';
import { DataPage } from '../../catalog/view/DataPage';
import { DisasterMode } from '../../disaster/view/DisasterMode';
import { CityExplorer } from '../../city/view/CityExplorer';
import { useGameInteractions } from '../../../shared/ui/useGameInteractions';
import './game-viewport.css';

const tabs = {
  city: '/weekly',
  missions: '/disaster',
  leaderboard: '/rankings',
  competitions: '/competitions',
  data: '/data',
  admin: '/admin/members',
  results: '/admin/results',
} as const;
type Tab = keyof typeof tabs;

export function GamePage() {
  useGameInteractions();
  const session = useAccountSession();
  const location = useAppLocation();
  const path = location.split('?')[0].replace(/\/$/, '') || '/';
  const tab = (Object.entries(tabs).find(
    ([, url]) =>
      path === url ||
      ((url === '/competitions' || url === '/disaster') && path.startsWith(url + '/'))
  )?.[0] ?? (path === '/' ? 'city' : 'missing')) as Tab | 'missing';
  const setTab = (id: Tab) => navigate(tabs[id]);
  const [cityDistrict, setCityDistrict] = useState('');
  const [auth, setAuth] = useState(false);
  useEffect(() => {
    if (path === '/') navigate('/weekly', true);
  }, [path]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [tab]);
  return (
    <div className={`game-shell${['city', 'missions'].includes(tab) ? ' is-game' : ''}`}>
      <header className="topbar">
        <a
          className="wordmark"
          href="/weekly"
          onClick={(e) => followLink(e, '/weekly')}
          aria-label="WATER LEAGUE 홈"
        >
          <svg width="31" height="31" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <path
              d="M3 10c5-6 10 6 15 0s8 0 11 0M3 17c5-6 10 6 15 0s8 0 11 0M3 24c5-6 10 6 15 0s8 0 11 0"
              stroke="currentColor"
              strokeWidth="3.4"
            />
          </svg>
          <span>
            WATER LEAGUE<small>시민의 설계, 도시의 변화</small>
          </span>
        </a>
        <nav aria-label="주요 화면">
          {(session.account?.role === 'ADMIN'
            ? ([
                ['admin', '회원 관리'],
                ['results', '결과 관리'],
                ['competitions', '대회'],
                ['data', '데이터'],
              ] as const)
            : ([
                ['city', '주간 서울 대항전'],
                ['missions', '재해 모드'],
                ['leaderboard', '랭킹'],
                ['competitions', '대회'],
                ['data', '데이터'],
              ] as const)
          ).map(([id, label]) => (
            <a
              href={tabs[id]}
              key={id}
              aria-current={tab === id ? 'page' : undefined}
              className={tab === id ? 'active' : ''}
              onClick={(e) => {
                if (id === 'city') setCityDistrict('');
                followLink(e, tabs[id]);
              }}
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="topbar-end">
          {session.account ? (
            <>
              <span className="account-name">
                {session.account.displayName}
                <small>
                  {session.account.role === 'ADMIN'
                    ? '관리자'
                    : memberTypeNames[session.account.memberType!]}
                </small>
              </span>
              <button
                className="icon-button"
                aria-label="로그아웃"
                disabled={session.busy}
                onClick={() => void session.signOut()}
              >
                <LogOut size={17} />
              </button>
            </>
          ) : (
            <button className="login-button" onClick={() => setAuth(true)}>
              로그인 <ArrowUpRight size={15} />
            </button>
          )}
        </div>
      </header>
      {session.error && (
        <div role="alert" className="global-message error">
          {session.error}
          <button aria-label="오류 알림 닫기" onClick={() => session.setError('')}>
            <X size={14} />
          </button>
        </div>
      )}
      {tab === 'admin' && session.account?.role === 'ADMIN' ? (
        <ApprovalPage key={session.account.id} />
      ) : tab === 'results' && session.account?.role === 'ADMIN' ? (
        <ResultsPage key={session.account.id} />
      ) : tab === 'competitions' ? (
        <CompetitionPage
          key={session.account?.id ?? 'guest'}
          account={session.account}
          onLogin={() => setAuth(true)}
        />
      ) : tab === 'city' ? (
        <CityExplorer
          key="shared"
          initialDistrictId={cityDistrict}
          account={session.account}
          onLogin={() => setAuth(true)}
          onAccount={session.setAccount}
        />
      ) : tab === 'missions' ? (
        <DisasterMode
          account={session.account}
          onLogin={() => setAuth(true)}
          onAccount={session.setAccount}
        />
      ) : tab === 'leaderboard' ? (
        <RankingPage
          account={session.account}
          onLogin={() => setAuth(true)}
          onWeeklyDistrict={(id) => {
            setCityDistrict(id);
            setTab('city');
          }}
        />
      ) : tab === 'data' ? (
        <DataPage accountId={session.account?.id ?? null} />
      ) : (
        <main className="full-page">
          <h1>{tab === 'missing' ? '페이지를 찾을 수 없습니다' : '관리자 로그인이 필요합니다'}</h1>
          <a href="/weekly" onClick={(e) => followLink(e, '/weekly')}>
            게임으로 돌아가기
          </a>
        </main>
      )}
      {auth && <AuthDialog onClose={() => setAuth(false)} onSuccess={session.setAccount} />}
    </div>
  );
}
