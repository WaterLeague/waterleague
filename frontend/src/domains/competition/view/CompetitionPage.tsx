import { useEffect, useState } from 'react';
import { Plus, Trophy, ArrowUpRight } from 'lucide-react';
import { isOrganizationMember, type Account } from '../../account/entity/account';
import { errorMessage } from '../../../shared/exception/ApiError';
import { useAppLocation, followLink, navigate } from '../../../shared/controller/useAppLocation';
import { loadCompetitionCatalog, loadCompetitions } from '../repository/competitionRepository';
import type { Competition, CompetitionCatalog } from '../dto/competitionDto';
import { CompetitionForm } from './CompetitionForm';
import { CompetitionDetail } from './CompetitionDetail';
import { Pagination, competitionTime, phaseNames } from './CompetitionShared';
import './competition.css';
import { SitePageHeader } from '../../../shared/ui/SitePageHeader';
export function CompetitionPage({
  account,
  onLogin,
}: {
  account: Account | null;
  onLogin: () => void;
}) {
  const location = useAppLocation(),
    path = location.split('?')[0].replace(/\/$/, '');
  const id = path.slice('/competitions/'.length);
  const detail = path.startsWith('/competitions/');
  const [catalog, setCatalog] = useState<CompetitionCatalog | null>(null),
    [items, setItems] = useState<Competition[]>([]),
    [page, setPage] = useState(0),
    [hasMore, setHasMore] = useState(false),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [creating, setCreating] = useState(false),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setError('');
    setLoading(true);
    void Promise.all([loadCompetitionCatalog(abort.signal), loadCompetitions(page, abort.signal)])
      .then(([c, list]) => {
        if (!abort.signal.aborted) {
          setCatalog(c);
          setItems(list.items);
          setHasMore(list.hasMore);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [page, detail, retry]);
  return (
    <main className="site-page contests-page">
      {error && (
        <div role="alert" className="contest-error">
          {error}{' '}
          <button className="outline-button" onClick={() => setRetry((v) => v + 1)}>
            다시 불러오기
          </button>
        </div>
      )}
      {detail && catalog ? (
        <CompetitionDetail key={id} id={id} account={account} catalog={catalog} onLogin={onLogin} />
      ) : (
        <>
          <SitePageHeader
            title="대회"
            description="정해진 지역과 시설, 기간 안에서 설계를 겨뤄보세요."
            action={
              isOrganizationMember(account) && (
                <button
                  className="solid-button"
                  disabled={!catalog}
                  onClick={() => setCreating((v) => !v)}
                >
                  <Plus size={17} />
                  대회 개최
                </button>
              )
            }
          />
          {creating && catalog && (
            <CompetitionForm
              catalog={catalog}
              onClose={() => setCreating(false)}
              onCreated={(c) => {
                setCreating(false);
                navigate(`/competitions/${c.id}`);
              }}
            />
          )}
          <p className="contest-note">
            승인된 기관·기업 회원이 대회를 개최합니다. 플레이어는 공개된 조건을 확인하고 참가할 수
            있습니다.
          </p>
          {loading ? (
            <p role="status">대회를 불러오는 중입니다.</p>
          ) : !items.length ? (
            <div className="contest-empty">
              <Trophy size={28} />
              <h2>아직 공개된 대회가 없습니다</h2>
              <p>개최된 대회는 이곳에서 일정과 참가 조건을 확인할 수 있습니다.</p>
            </div>
          ) : (
            <div className="contest-cards">
              {items.map((c) => {
                const href = `/competitions/${c.id}`;
                return (
                  <a
                    className="contest-card"
                    key={c.id}
                    href={href}
                    onClick={(e) => followLink(e, href)}
                  >
                    <div className="contest-heading">
                      <span className="contest-badge">{phaseNames[c.phase]}</span>
                      <ArrowUpRight size={19} />
                    </div>
                    <small>
                      {c.organizationName} · {c.mode === 'REALTIME' ? '실시간 모드' : '재해 모드'}
                    </small>
                    <h2>{c.title}</h2>
                    <p>{c.description}</p>
                    <footer>
                      <span>
                        {competitionTime(c.opensAt)} —<br />
                        {competitionTime(c.closesAt)}
                      </span>
                      <span>
                        {c.participantCount}명 참가{c.joinedAt && ' · 참가 중'}
                        {c.canManage && ' · 관리'}
                      </span>
                    </footer>
                  </a>
                );
              })}
            </div>
          )}
          {!loading && <Pagination page={page} hasMore={hasMore} onPage={setPage} />}
        </>
      )}
    </main>
  );
}
