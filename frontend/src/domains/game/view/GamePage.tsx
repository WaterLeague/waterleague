import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, LogOut, X } from 'lucide-react';
import { useAccountSession } from '../../account/controller/useAccountSession';
import { memberTypeNames } from '../../account/entity/account';
import { AuthDialog } from '../../account/view/AuthDialog';
import { ApprovalPage } from '../../administration/view/ApprovalPage';
import { CompetitionPage } from '../../league/view/CompetitionPage';
import { DataPage } from '../../catalog/view/DataPage';
import { DisasterMode } from '../../disaster/view/DisasterMode';
import { CityExplorer } from '../../city/view/CityExplorer';
import { FullscreenButton } from './FullscreenButton';
import { useGameInteractions } from '../../../shared/ui/useGameInteractions';
import './game-viewport.css';

type Tab = 'city' | 'missions' | 'leaderboard' | 'data' | 'admin';

export function GamePage() {
  useGameInteractions();
  const session = useAccountSession();
  const shell = useRef<HTMLDivElement>(null);
  const [cityDistrict, setCityDistrict] = useState('');
  const [tab, setTab] = useState<Tab>('city');
  const [auth, setAuth] = useState(false);
  useEffect(() => {
    if (session.account?.role === 'ADMIN') setTab('admin');
    else setTab((current) => (current === 'admin' ? 'missions' : current));
  }, [session.account?.id, session.account?.role]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [tab]);
  return (
    <div
      ref={shell}
      className={`game-shell${['city', 'missions'].includes(tab) ? ' is-game' : ''}`}
    >
      <header className="topbar">
        <a className="wordmark" href="/" aria-label="WATER LEAGUE 홈">
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
                ['data', '데이터'],
              ] as const)
            : ([
                ['city', '주간 서울 대항전'],
                ['missions', '재해 모드'],
                ['leaderboard', '기록 경쟁'],
                ['data', '데이터'],
              ] as const)
          ).map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? 'page' : undefined}
              className={tab === id ? 'active' : ''}
              onClick={() => {
                if (id === 'city') setCityDistrict('');
                setTab(id);
              }}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="topbar-end">
          {['city', 'missions'].includes(tab) && <FullscreenButton target={shell} />}
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
        <CompetitionPage
          account={session.account}
          onLogin={() => setAuth(true)}
          onWeeklyDistrict={(id) => {
            setCityDistrict(id);
            setTab('city');
          }}
        />
      ) : (
        <DataPage accountId={session.account?.id ?? null} />
      )}
      {auth && <AuthDialog onClose={() => setAuth(false)} onSuccess={session.setAccount} />}
    </div>
  );
}
