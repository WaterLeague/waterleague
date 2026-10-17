import { useState, useEffect, useRef } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  CloudRain,
  Layers3,
  Plus,
  Undo2,
  Redo2,
  Save,
  Play,
  Check,
  Trash2,
  Leaf,
  Grid2X2,
  House,
  LogOut,
  Download,
  Trophy,
  Info,
  FolderOpen,
  Menu,
  X,
  Database,
  CircleHelp,
} from 'lucide-react';
import { rainfallLabel } from '../service/modelFamilyService';
import { useGame } from '../controller/useGame';
import { useCatalog } from '../../catalog/controller/useCatalog';
import type { FacilityType } from '../entity/game';
import { facilities, format, won, totalCost } from '../service/gameService';
import * as repo from '../repository/gameRepository';
import { logout } from '../../account/repository/accountRepository';
import { ApprovalPage } from '../../administration/view/ApprovalPage';
import { memberTypeNames } from '../../account/entity/account';
import { AuthDialog } from '../../account/view/AuthDialog';
import { RainfallSelector, rainDate, rainTime } from './RainfallSelector';
import { Hydrograph } from './Hydrograph';
import { CompetitionPage } from '../../league/view/CompetitionPage';
import type { League } from '../../league/entity/league';
import { exceedsLeagueLimits, totalArea } from '../../league/service/leagueService';
import { ResearchPage } from '../../research/view/ResearchPage';
import { SpatialComparison } from '../../spatial/view/SpatialComparison';
import { MapViewport } from '../../catalog/view/MapViewport';
import { ChallengeLobby } from './ChallengeLobby';
import { RoundReport } from './RoundReport';
import { matchesEvaluatedDesign } from '../service/roundService';
import { assessPlacementDraft } from '../service/placementDraftService';
import { PlayGuide } from './PlayGuide';
import { CityExplorer } from '../../city/view/CityExplorer';
const icons = { RAIN_GARDEN: Leaf, PERMEABLE_PAVEMENT: Grid2X2, GREEN_ROOF: House };
export function GamePage() {
  const g = useGame();
  const catalog = useCatalog();
  const [tab, setTab] = useState<
    'city' | 'missions' | 'studio' | 'leaderboard' | 'research' | 'data' | 'admin'
  >('city');
  const [report, setReport] = useState(false);
  const [feedback, setFeedback] = useState('');
  const playHeading = useRef<HTMLHeadingElement>(null);
  const [showGuide, setShowGuide] = useState(true);
  const guideToggle = useRef<HTMLButtonElement>(null);
  const calculateButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setReport(g.job?.state === 'SUCCEEDED');
  }, [g.job?.id, g.job?.state]);
  const [selected, setSelected] = useState<string | null>(null),
    [type, setType] = useState<FacilityType>('RAIN_GARDEN'),
    [area, setArea] = useState(40);
  const [auth, setAuth] = useState(false),
    [showList, setShowList] = useState(false),
    [showSaves, setShowSaves] = useState(false);
  const listToggle = useRef<HTMLButtonElement>(null);
  const listPanel = useRef<HTMLDivElement>(null);
  const areaInput = useRef<HTMLInputElement>(null);
  const [focusEditor, setFocusEditor] = useState(false);
  useEffect(() => {
    if (showList) {
      const panel = listPanel.current;
      (
        panel?.querySelector<HTMLButtonElement>('[aria-pressed="true"]') ??
        panel?.querySelector<HTMLButtonElement>('[aria-pressed]')
      )?.focus();
    }
  }, [showList]);
  useEffect(() => {
    if (focusEditor && areaInput.current) {
      areaInput.current.focus();
      setFocusEditor(false);
    }
  }, [focusEditor, selected]);
  function closeList() {
    setShowList(false);
    listToggle.current?.focus();
  }
  useEffect(() => {
    if (g.account?.role === 'ADMIN') setTab('admin');
    else setTab((t) => (t === 'admin' ? 'missions' : t));
  }, [g.account?.id, g.account?.role]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [tab]);
  const [activeLeague, setActiveLeague] = useState<League | null>(null);
  const lab = g.lab;
  useEffect(() => {
    setSelected(null);
    setFeedback('');
  }, [lab?.modelHash]);
  const mapEntry = catalog.data?.maps.find((entry) =>
    entry.modelHashes.includes(lab?.modelHash ?? '')
  );
  const activeMap = mapEntry?.map ?? null;
  const mapError =
    catalog.error ||
    (catalog.data && lab && !activeMap ? '이 모델에 연결된 지도 버전을 찾을 수 없습니다.' : '');
  useEffect(() => {
    if (activeLeague && lab && activeLeague.rules.modelHash !== lab.modelHash)
      setActiveLeague(null);
  }, [lab?.modelHash, activeLeague]);
  const budget = activeLeague?.rules.budget ?? lab?.model.budget ?? 0;
  const allowedTypes =
    activeLeague?.rules.allowedTypes ?? (Object.keys(facilities) as FacilityType[]);
  const cell = lab?.model.cells.find((c) => c.id === selected);
  const placement = g.placements.find((p) => p.cellId === selected);
  useEffect(() => {
    if (placement) {
      setType(placement.facilityType);
      setArea(placement.areaM2);
    }
  }, [selected, placement?.facilityType, placement?.areaM2]);
  const placementLimits = {
    placementLimit: activeLeague?.rules.placementLimit ?? lab?.model.maxPlacements ?? 0,
    areaLimitM2: activeLeague?.rules.areaLimitM2,
  };
  const currentExceedsLimits = exceedsLeagueLimits(g.placements, placementLimits);
  const draft = lab
    ? assessPlacementDraft(lab, g.placements, selected, type, area, {
        ...placementLimits,
        budget,
        allowedTypes,
      })
    : null;
  const draftArea = draft?.areaM2 ?? 0;
  const cost = lab ? totalCost(lab, g.placements) : 0;
  const canPlace = !!draft?.placement && !g.busy;
  const preview =
    canPlace && cell && (placement?.facilityType !== type || placement?.areaM2 !== draftArea)
      ? { cellId: cell.id, facilityType: type, areaM2: draftArea }
      : undefined;
  function undo() {
    g.undo();
    setFeedback('배치 변경을 되돌렸습니다.');
  }
  function redo() {
    g.redo();
    setFeedback('배치 변경을 다시 적용했습니다.');
  }
  function select(id: string | null) {
    setFeedback('');
    const c = lab?.model.cells.find((c) => c.id === id || c.buildingId === id);
    setSelected(c?.id ?? null);
    if (c) {
      const p = g.placements.find((p) => p.cellId === c.id);
      setType(
        p?.facilityType ?? c.allowedTypes.find((t) => allowedTypes.includes(t)) ?? c.allowedTypes[0]
      );
      setArea(p?.areaM2 ?? Math.min(40, c.maxAreaM2));
    }
  }
  const result = g.job?.result;
  const currentResult = lab
    ? matchesEvaluatedDesign(g.job, g.evaluatedVersion, lab.modelHash, g.placements)
    : false;
  const working = g.busy || g.job?.state === 'QUEUED' || g.job?.state === 'RUNNING';
  const showCurrentResult =
    !!result &&
    g.job?.state === 'SUCCEEDED' &&
    currentResult &&
    !preview &&
    (!cell || !draft?.issue);
  const guideStep = working
    ? 2
    : cell && (preview || draft?.issue)
      ? 1
      : g.placements.length
        ? 2
        : cell
          ? 1
          : 0;
  return (
    <div
      className={`game-shell${tab === 'missions' ? ' in-challenge' : ''}${tab === 'studio' ? ' in-play' : ''}`}
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
          {(g.account?.role === 'ADMIN'
            ? ([
                ['admin', '회원 관리'],
                ['data', '데이터'],
              ] as const)
            : ([
                ['city', '서울 지도'],
                ['missions', '도전'],
                ...(tab === 'studio' ? ([['studio', '플레이']] as const) : []),
                ['leaderboard', '기록 경쟁'],
                ['research', '연구실'],
                ['data', '데이터'],
              ] as const)
          ).map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? 'page' : undefined}
              className={tab === id ? 'active' : ''}
              onClick={() => {
                setTab(id);
                g.setNotice('');
              }}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="topbar-end">
          {g.account ? (
            <>
              <span className="account-name">
                {g.account.displayName}
                <small>
                  {g.account.role === 'ADMIN' ? '관리자' : memberTypeNames[g.account.memberType!]}
                </small>
              </span>
              <button
                className="icon-button"
                aria-label="로그아웃"
                onClick={() =>
                  void g.action(async () => {
                    await logout();
                    g.setAccount(null);
                    g.newDesign();
                    setActiveLeague(null);
                  })
                }
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
      {lab &&
        g.rainfallCatalog &&
        g.account?.role !== 'ADMIN' &&
        tab !== 'missions' &&
        tab !== 'city' &&
        tab !== 'studio' && (
          <RainfallSelector
            lab={lab}
            catalog={g.rainfallCatalog}
            disabled={working || !!activeLeague}
            onChange={(hash) =>
              void g.action(async () => {
                await g.selectModel(hash);
                setSelected(null);
              })
            }
          />
        )}
      {activeLeague && tab === 'studio' && (
        <div className="active-league-banner">
          <div>
            <span>기관 리그 설계</span>
            <b>{activeLeague.title}</b>
            <small>
              예산 {won(budget)} · {allowedTypes.map((t) => facilities[t].name).join(' · ')}
              {activeLeague.rules.placementLimit != null && (
                <>
                  {' '}
                  · 최대 {activeLeague.rules.placementLimit}개 구역 ·{' '}
                  {format.format(activeLeague.rules.areaLimitM2 ?? 0)} m²
                </>
              )}
            </small>
          </div>
          <button className="outline-button" onClick={() => setTab('leaderboard')}>
            고정 규칙·제출
          </button>
          <button className="text-button" onClick={() => setActiveLeague(null)}>
            일반 설계로 전환
          </button>
        </div>
      )}
      {g.error && (
        <div role="alert" className="global-message error">
          {g.error}
          <button aria-label="오류 알림 닫기" onClick={() => g.setError('')}>
            <X size={14} />
          </button>
        </div>
      )}
      {g.notice && (
        <div role="status" className="global-message">
          <Check size={15} />
          {g.notice}
          <button aria-label="알림 닫기" onClick={() => g.setNotice('')}>
            <X size={14} />
          </button>
        </div>
      )}
      {tab === 'city' ? (
        <CityExplorer
          busy={working || g.loading}
          onPlay={(modelHash) => {
            const hash = modelHash ?? g.rainfallCatalog?.defaultModelHash;
            if (!hash) {
              g.setError('도전 목록을 불러온 뒤 다시 선택해 주세요.');
              return;
            }
            void g.action(async () => {
              if (hash !== lab?.modelHash && !(await g.selectModel(hash))) return;
              setSelected(null);
              setActiveLeague(null);
              setFeedback('');
              setTab('missions');
            });
          }}
        />
      ) : !lab ? (
        <div className="empty-state">
          <CloudRain size={38} />
          <h2>{g.loading ? '설계실을 준비하고 있습니다.' : '서버에 연결할 수 없습니다.'}</h2>
          <p>
            {g.loading
              ? '공개자료와 실험 조건을 불러오는 중'
              : 'API 실행 상태를 확인한 뒤 다시 불러오세요.'}
          </p>
          {!g.loading && (
            <button className="outline-button" onClick={() => location.reload()}>
              다시 불러오기
            </button>
          )}
        </div>
      ) : tab === 'admin' && g.account?.role === 'ADMIN' ? (
        <ApprovalPage key={g.account.id} />
      ) : tab === 'missions' ? (
        <ChallengeLobby
          lab={lab}
          catalog={g.rainfallCatalog}
          map={activeMap}
          busy={working}
          hasDesign={g.placements.length > 0}
          league={activeLeague}
          onFreePlay={() => setActiveLeague(null)}
          onSelect={(hash) => {
            if (hash !== lab.modelHash)
              void g.action(async () => {
                await g.selectModel(hash);
                setSelected(null);
                setActiveLeague(null);
                setFeedback('');
              });
          }}
          onPlay={() => setTab('studio')}
          onCompetition={() => setTab('leaderboard')}
          onEvidence={() => setTab('data')}
        />
      ) : tab === 'studio' ? (
        <div className="studio-layout play-layout">
          <header className="play-hud">
            <div className="play-objective">
              <span>
                {lab.model.mapTitle ?? '성수'} / {activeLeague ? '기관 리그' : '일반 도전'}
              </span>
              <h1 ref={playHeading} tabIndex={-1}>
                {activeLeague?.title ?? '빗물이 머물 자리를 만드세요'}
              </h1>
              <small>
                {rainDate(lab.model.rainfall.start)} · {lab.model.rainfall.stationName} ·{' '}
                {lab.model.rainfall.totalDepthMm} mm
                {lab.model.regionalRainfallUse &&
                  ` · ${rainfallLabel(lab.model.regionalRainfallUse)}`}
              </small>
            </div>
            <div className="play-resources">
              <span>
                {report ? '계산한 배치 비용' : '남은 예산'}{' '}
                <b>{won(report && g.evaluatedVersion ? g.evaluatedVersion.cost : budget - cost)}</b>
              </span>
              <span>
                배치 구역{' '}
                <b>
                  {report && g.evaluatedVersion
                    ? g.evaluatedVersion.placements.length
                    : g.placements.length}
                  <small> / {placementLimits.placementLimit}</small>
                </b>
              </span>
            </div>
            <div className="play-phase" aria-label="도전 진행 단계">
              <span className={!working && !report ? 'active' : ''}>01 배치</span>
              <ArrowRight size={12} />
              <span className={working ? 'active' : ''}>02 계산</span>
              <ArrowRight size={12} />
              <span className={report ? 'active' : ''}>03 결과</span>
            </div>
            <button
              ref={guideToggle}
              className="play-help"
              aria-expanded={showGuide && !report}
              aria-controls="play-guide"
              onClick={() => {
                setReport(false);
                setShowGuide((value) => report || !value);
              }}
            >
              <CircleHelp size={16} /> 플레이 안내
            </button>
          </header>
          {!report && showGuide && (
            <PlayGuide
              step={guideStep}
              pending={
                g.job?.state === 'QUEUED' || g.job?.state === 'RUNNING'
                  ? g.job.state
                  : g.busy
                    ? 'REQUEST'
                    : null
              }
              signedIn={!!g.account}
              currentResult={showCurrentResult}
              onChoose={() => setShowList(true)}
              onEdit={() => setFocusEditor(true)}
              onCalculate={() => {
                if (showCurrentResult) setReport(true);
                else calculateButton.current?.focus();
              }}
              onClose={() => {
                setShowGuide(false);
                guideToggle.current?.focus();
              }}
            />
          )}
          {report && g.job?.state === 'SUCCEEDED' && result ? (
            <RoundReport
              key={g.job.id}
              job={g.job}
              lab={lab}
              map={activeMap}
              evaluated={g.evaluatedVersion}
              current={currentResult}
              busy={g.busy}
              league={!!activeLeague}
              onRetry={() => {
                setReport(false);
                requestAnimationFrame(() => playHeading.current?.focus());
              }}
              onSubmit={() =>
                void g.action(async () => {
                  if (activeLeague) {
                    setTab('leaderboard');
                    return;
                  }
                  await repo.submit(g.job!.id);
                  g.setNotice('탐색 기록 제출 완료');
                })
              }
              onBoard={() => setTab('leaderboard')}
            />
          ) : (
            <>
              <main className="design-main">
                <div className="design-toolbar">
                  <div className="design-title">
                    <input
                      aria-label="설계 이름"
                      maxLength={80}
                      value={g.title}
                      onChange={(e) => g.setTitle(e.target.value)}
                    />
                    <span>{g.version ? `저장 버전 ${g.version.revision}` : '새 설계'}</span>
                  </div>
                  <div>
                    <button
                      className="icon-button"
                      aria-label="새 설계"
                      onClick={() => {
                        g.newDesign();
                        select(null);
                        setFeedback('');
                      }}
                    >
                      <Plus size={18} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label="저장한 설계"
                      onClick={() => setShowSaves((v) => !v)}
                    >
                      <FolderOpen size={18} />
                    </button>
                    <button
                      className="outline-button compact"
                      disabled={g.busy}
                      onClick={() => (g.account ? void g.action(g.save) : setAuth(true))}
                    >
                      <Save size={14} />
                      저장
                    </button>
                  </div>
                </div>
                <section
                  className="design-stage"
                  aria-label="시설 배치 지도"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (
                      g.busy ||
                      e.altKey ||
                      (!e.ctrlKey && !e.metaKey) ||
                      (e.target instanceof Element &&
                        e.target.closest(
                          'input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]'
                        ))
                    )
                      return;
                    const key = e.key.toLowerCase();
                    const isRedo = (key === 'z' && e.shiftKey) || (key === 'y' && e.ctrlKey);
                    if (isRedo && g.canRedo) {
                      e.preventDefault();
                      redo();
                    } else if (key === 'z' && !e.shiftKey && g.canUndo) {
                      e.preventDefault();
                      undo();
                    }
                  }}
                >
                  <div className="scene-overline">
                    <span>
                      <i />
                      공개 건물 경계
                    </span>
                    <span>표고 평탄화 · 설치 가능성 가정</span>
                  </div>
                  {mapError ? (
                    <div className="empty-state">
                      <p>{mapError}</p>
                      <button onClick={catalog.retry}>다시 시도</button>
                    </div>
                  ) : activeMap ? (
                    <MapViewport
                      key={activeMap.snapshot.id}
                      map={activeMap}
                      cells={lab.model.cells}
                      placements={g.placements}
                      preview={preview}
                      selectedCell={selected}
                      onSelect={(id) => {
                        select(id);
                        if (id) setFocusEditor(true);
                      }}
                    />
                  ) : (
                    <div className="empty-state">실제 건물 경계 불러오는 중</div>
                  )}
                  <div className="scene-controls">
                    <button
                      ref={listToggle}
                      aria-label="구역 목록"
                      aria-expanded={showList}
                      aria-controls="design-cell-list"
                      onClick={() => setShowList((v) => !v)}
                    >
                      <Menu size={18} />
                    </button>
                  </div>
                  {showList && (
                    <div
                      id="design-cell-list"
                      className="cell-list"
                      ref={listPanel}
                      role="region"
                      aria-label="실험 구역 선택"
                      onKeyDown={(event) => {
                        if (event.key === 'Escape') {
                          event.preventDefault();
                          closeList();
                        }
                      }}
                    >
                      <div className="cell-list-heading">
                        <b>실험 구역 선택</b>
                        <button
                          className="icon-button"
                          aria-label="구역 목록 닫기"
                          onClick={closeList}
                        >
                          <X size={15} />
                        </button>
                      </div>
                      {lab.model.cells.map((c) => (
                        <button
                          key={c.id}
                          className={c.id === selected ? 'selected' : ''}
                          aria-pressed={c.id === selected}
                          aria-label={`${c.id} · ${c.name} · ${g.placements.some((p) => p.cellId === c.id) ? '배치됨' : '미배치'}`}
                          onClick={() => {
                            select(c.id);
                            setShowList(false);
                            setFocusEditor(true);
                          }}
                        >
                          <span>
                            {c.id} · {c.name}
                          </span>
                          {g.placements.some((p) => p.cellId === c.id) ? (
                            <Check size={14} />
                          ) : (
                            <ArrowRight size={14} />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                  {showSaves && (
                    <div className="saved-list">
                      <div>
                        <b>저장한 설계</b>
                        <button
                          className="icon-button"
                          aria-label="저장 목록 닫기"
                          onClick={() => setShowSaves(false)}
                        >
                          <X size={15} />
                        </button>
                      </div>
                      {g.strategies.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => {
                            void g.open(s.id);
                            setShowSaves(false);
                          }}
                        >
                          <b>{s.title}</b>
                          <span>버전 {s.revision}</span>
                        </button>
                      ))}
                      {!g.strategies.length && (
                        <p>
                          {g.account
                            ? '저장한 설계가 없습니다.'
                            : '로그인하면 설계를 저장할 수 있습니다.'}
                        </p>
                      )}
                    </div>
                  )}
                  <div className="facility-dock">
                    {allowedTypes.map((t) => {
                      const Icon = icons[t];
                      return (
                        <button
                          key={t}
                          className={type === t ? 'selected' : ''}
                          aria-pressed={type === t}
                          aria-label={facilities[t].name}
                          title={facilities[t].name}
                          onClick={() => {
                            setFeedback('');
                            setType(t);
                            if (!cell?.allowedTypes.includes(t)) {
                              const c = lab.model.cells.find((c) => c.allowedTypes.includes(t));
                              if (c) {
                                select(c.id);
                                setType(t);
                              }
                            }
                          }}
                        >
                          <Icon size={20} />
                          <span>{facilities[t].name}</span>
                        </button>
                      );
                    })}
                    <button
                      className="history-button undo-button"
                      aria-label="마지막 배치 변경 되돌리기"
                      aria-keyshortcuts="Control+Z Meta+Z"
                      title="배치 되돌리기 · Ctrl/⌘ Z"
                      disabled={g.busy || !g.canUndo}
                      onClick={undo}
                    >
                      <Undo2 size={18} />
                    </button>
                    <button
                      className="history-button"
                      aria-label="되돌린 배치 변경 다시 실행"
                      aria-keyshortcuts="Control+Shift+Z Meta+Shift+Z Control+Y"
                      title="배치 다시 실행 · Ctrl/⌘ Shift Z"
                      disabled={g.busy || !g.canRedo}
                      onClick={redo}
                    >
                      <Redo2 size={18} />
                    </button>
                  </div>
                </section>
                <details className="play-chart">
                  <summary>관측 강우·계산 흐름 확인</summary>
                  <Hydrograph job={g.job} rainfall={lab.model.rainfall} />
                </details>
                <div className="studio-footnote">
                  <span>
                    <i />
                    탐색 모델 · 현장 미검증
                  </span>
                  <button className="text-button" onClick={() => setTab('data')}>
                    자료·가정 확인 <ArrowUpRight size={12} />
                  </button>
                </div>
              </main>
              <aside className="inspector" aria-label="시설 편집과 도전 실행">
                <p className="placement-feedback" role="status">
                  {feedback ||
                    (cell
                      ? '시설과 면적을 정한 뒤 배치하세요.'
                      : '시설을 고르거나 지도에서 구역을 선택하세요.')}
                </p>
                <div className="inspector-top">
                  <span className="eyebrow">
                    {cell ? 'DESIGN A SURFACE' : 'BUILD YOUR STRATEGY'}
                  </span>
                  <Layers3 size={17} />
                </div>
                <h2>
                  {cell
                    ? cell.name
                    : g.placements.length
                      ? '다음 수를 선택하세요'
                      : '첫 시설을 배치하세요'}
                </h2>
                <p className="panel-intro">
                  {cell
                    ? '설치할 시설과 면적을 선택하세요. 공개 사업계획 참고 단가로 비용을 계산합니다.'
                    : '지도에서 표시된 구역을 선택하거나, 시설 도구로 첫 배치를 시작하세요.'}
                </p>
                {cell ? (
                  <>
                    <div className="cell-tag">
                      <span>
                        {cell.id} · {cell.kind === 'ROOF' ? '옥상' : '지상'} 실험 단위
                      </span>
                      <b>현장 적합성 미확인</b>
                    </div>
                    {activeLeague && !cell.allowedTypes.some((t) => allowedTypes.includes(t)) && (
                      <p className="form-error">
                        이 구역에는 리그에서 허용한 시설을 설치할 수 없습니다. 다른 구역을
                        선택하세요.
                      </p>
                    )}
                    <div className="facility-options">
                      {cell.allowedTypes
                        .filter((t) => allowedTypes.includes(t))
                        .map((t) => {
                          const Icon = icons[t];
                          return (
                            <button
                              key={t}
                              className={type === t ? 'active' : ''}
                              aria-pressed={type === t}
                              onClick={() => {
                                setType(t);
                                setFeedback('');
                              }}
                            >
                              <Icon size={18} />
                              {facilities[t].name}
                            </button>
                          );
                        })}
                    </div>
                    <p className="facility-description">{facilities[type].description}</p>
                    <label className="area-input">
                      설치 면적{' '}
                      <span>
                        <input
                          ref={areaInput}
                          type="number"
                          min="0.01"
                          max={cell.maxAreaM2}
                          step="0.01"
                          value={area}
                          aria-invalid={!!draft?.issue}
                          aria-describedby="placement-draft-note"
                          onChange={(e) => {
                            setArea(Number(e.target.value));
                            setFeedback('');
                          }}
                        />{' '}
                        m²
                      </span>
                    </label>
                    <input
                      className="area-slider"
                      aria-label="설치 면적 조절"
                      type="range"
                      min="0.01"
                      max={cell.maxAreaM2}
                      step="0.01"
                      value={area}
                      aria-describedby="placement-draft-note"
                      onChange={(e) => {
                        setArea(Number(e.target.value));
                        setFeedback('');
                      }}
                    />
                    <div className="area-range">
                      <span>0.01 m²</span>
                      <span>최대 {format.format(cell.maxAreaM2)} m²</span>
                    </div>
                    <div className="placement-cost">
                      <span>추정 설치비</span>
                      <strong>
                        {Number.isFinite(draftArea) && draftArea > 0
                          ? won(draftArea * lab.model.unitCosts[type])
                          : '—'}
                      </strong>
                    </div>
                    {preview && draft?.projectedCost != null && (
                      <p className="draft-cost">
                        확정하면 총 {won(draft.projectedCost)} · 아직 반영 전
                      </p>
                    )}
                    <p
                      id="placement-draft-note"
                      className={draft?.issue ? 'form-error' : 'draft-note'}
                      role="status"
                    >
                      {draft?.message ||
                        (preview
                          ? '미리보기 중입니다. 배치 버튼을 눌러 확정하세요.'
                          : '이 구역의 확정 배치와 같은 설정입니다.')}
                    </p>
                    <button
                      className="primary-button"
                      disabled={!canPlace}
                      onClick={() => {
                        g.change([
                          ...g.placements.filter((p) => p.cellId !== cell.id),
                          {
                            cellId: cell.id,
                            facilityType: type,
                            areaM2: draftArea,
                          },
                        ]);
                        setFeedback(
                          `${cell.id} · ${facilities[type].name} ${format.format(draftArea)} m² ${placement ? '변경' : '배치'} 완료`
                        );
                      }}
                    >
                      {placement ? '배치 변경' : '이 구역에 배치'}
                      <Plus size={16} />
                    </button>
                    {placement && (
                      <button
                        className="text-button remove-button"
                        onClick={() => {
                          g.change(g.placements.filter((p) => p.cellId !== cell.id));
                          setFeedback(`${cell.id} 시설 제거 완료`);
                        }}
                      >
                        <Trash2 size={14} />이 시설 제거
                      </button>
                    )}
                  </>
                ) : (
                  <div className="facility-primer">
                    {allowedTypes.map((facilityType) => {
                      const Icon = icons[facilityType];
                      return (
                        <div key={facilityType}>
                          <b>
                            <Icon size={17} />
                            {facilities[facilityType].name}
                          </b>
                          <p>{facilities[facilityType].intro}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="budget-box">
                  <div>
                    <span>추정 비용</span>
                    <b>
                      {won(cost)}
                      <small> / {won(budget)}</small>
                    </b>
                  </div>
                  <div className="budget-track">
                    <i style={{ width: Math.min(100, (cost / budget) * 100) + '%' }} />
                  </div>
                  <span>
                    {g.placements.length}개 시설 · 합계 {format.format(totalArea(g.placements))} m²
                    · 공개계획 참고 단가 · 부대비용 별도
                  </span>
                </div>
                <details className="play-note">
                  <summary>이 선택을 한 이유 남기기</summary>
                  <label className="design-note">
                    설계 메모
                    <textarea
                      maxLength={2000}
                      rows={2}
                      value={g.note}
                      onChange={(e) => g.setNote(e.target.value)}
                      placeholder="어떤 선택을 했고, 왜 그렇게 배치했나요?"
                    />
                  </label>
                </details>
                <button
                  ref={calculateButton}
                  className="simulate-button"
                  disabled={
                    working ||
                    !lab.model.simulationAvailable ||
                    cost > budget ||
                    currentExceedsLimits ||
                    g.placements.some((p) => !allowedTypes.includes(p.facilityType))
                  }
                  onClick={() => (g.account ? void g.run() : setAuth(true))}
                >
                  <Play size={17} />
                  {working
                    ? g.job?.state === 'QUEUED'
                      ? '계산 순서 대기'
                      : '서버에서 계산 중'
                    : preview
                      ? '확정된 배치로 도전'
                      : g.placements.length
                        ? '이 배치로 도전'
                        : '시설 없는 기준안 계산'}
                  <ArrowRight size={16} />
                </button>
                {g.job?.state === 'FAILED' || g.job?.state === 'REJECTED' ? (
                  <p className="form-error" role="alert">
                    계산이 품질 검사를 통과하지 못했습니다. 코드: {g.job.errorCode}
                  </p>
                ) : null}
                {working && (
                  <p className="play-computing" role="status">
                    {g.job?.state === 'QUEUED'
                      ? '앞선 계산이 끝나면 시작합니다.'
                      : '실제 관측 강우로 SWMM을 실행하고 품질을 확인합니다.'}{' '}
                    완료되면 결과 화면으로 이동합니다.
                  </p>
                )}
                {result && (
                  <button
                    className="outline-button previous-result"
                    onClick={() => setReport(true)}
                  >
                    <Trophy size={15} />{' '}
                    {currentResult ? '계산 결과 다시 보기' : '이전 배치의 결과 보기'}
                  </button>
                )}
              </aside>
            </>
          )}
        </div>
      ) : tab === 'leaderboard' ? (
        <CompetitionPage
          account={g.account}
          lab={lab}
          initialLeague={!!activeLeague}
          version={g.version}
          catalog={g.rainfallCatalog}
          onStudio={() => setTab('studio')}
          onOpen={(id) => {
            void g.open(id).then(() => {
              setActiveLeague(null);
              setSelected(null);
              setTab('studio');
            });
          }}
          onDesign={(l) => {
            void g.action(async () => {
              if (!(await g.selectModel(l.rules.modelHash, false))) return;
              g.newDesign();
              setActiveLeague(l);
              setSelected(null);
              setType(l.rules.allowedTypes[0]);
              g.setTitle(l.title.slice(0, 76) + ' 설계');
              setTab('studio');
            });
          }}
        />
      ) : tab === 'research' ? (
        <ResearchPage
          key={(g.account?.id ?? 'guest') + ':' + lab.modelHash}
          account={g.account}
          lab={lab}
          catalog={g.rainfallCatalog}
          map={activeMap}
          onReplay={(p) => {
            g.newDesign();
            setActiveLeague(null);
            g.change(p);
            g.setTitle('연구 기록 배치 검토');
            setTab('studio');
            g.setNotice(
              '연구 기록의 배치를 불러왔습니다. 저장하면 내 설계로 새 버전이 생성됩니다.'
            );
          }}
        />
      ) : (
        <section className="full-page evidence-page">
          <div className="page-eyebrow">
            DATA & EVIDENCE <span>PUBLIC SOURCES</span>
          </div>
          <h1>
            현실을 닮으려면,
            <br />
            가정부터 드러내야 합니다.
          </h1>
          <p className="lead">공개 원본, 처리 과정, 아직 모르는 부분을 함께 남깁니다.</p>
          <div className="evidence-grid">
            <article>
              <CloudRain />
              <span className="state done">실제 관측 · 자체 QC 통과</span>
              <h2>기상청 {lab.model.rainfall.stationName} 분강우</h2>
              <strong>
                {lab.model.rainfall.totalDepthMm}
                <small> mm</small>
              </strong>
              <p>
                {rainTime(lab.model.rainfall.start)} ~ {rainTime(lab.model.rainfall.end)} KST.
                {lab.model.rainfall.depthsMm.length + 1}개 누적 관측에서{' '}
                {lab.model.rainfall.depthsMm.length}분 깊이 추출. 결측·음수·자정 경계 검사와
                이동누적 교차 확인.
              </p>
              {lab.model.rainfall.stationDistanceKm !== undefined && (
                <p>
                  구역 중심과 약 {lab.model.rainfall.stationDistanceKm.toFixed(2)} km.{' '}
                  {lab.model.rainfall.stationDistanceEvidence}
                </p>
              )}
              {lab.model.rainfall.windowStatistics && (
                <p>
                  최대 15분 {lab.model.rainfall.windowStatistics.peak15MinuteMm} mm · 최대 60분{' '}
                  {lab.model.rainfall.windowStatistics.peak60MinuteMm} mm. 마지막 강우 후 관측
                  무강우 {lab.model.rainfall.windowStatistics.observedDryTailMinutes}분.
                </p>
              )}
              <a href={`/api/v1/lab?modelHash=${lab.modelHash}`} download>
                관측 파생자료 <Download size={14} />
              </a>
            </article>
            <article>
              <Database />
              <span className="state done">공개 공간자료</span>
              <h2>{lab.model.mapTitle ?? '성수동'} 공개 건물 경계</h2>
              <strong>
                {activeMap?.buildings.length ?? '—'}
                <small>개</small>
              </strong>
              <p>
                {activeMap?.snapshot.title} · {activeMap?.snapshot.subtitle}
              </p>
              <p>
                {activeMap?.snapshot.limitations
                  .filter(
                    (text) =>
                      !lab.model.regionalRainfallUse || !text.includes('성동 관측 강우 공통 재생')
                  )
                  .join(' · ')}
              </p>
              <a href={mapEntry ? `/data/${mapEntry.file}` : undefined} download>
                공간 파생자료 <Download size={14} />
              </a>
            </article>
          </div>
          <div className="scope-note">
            <Info size={20} />
            <p>
              <b>현장 연구 적용 전</b> · 실제 배수경계·관망·지표고·토양·독립 유출 관측으로 보정과
              검증이 필요합니다. 현재 점수로 공사 효과나 홍수위험을 결정할 수 없습니다.
            </p>
          </div>
          {catalog.data && (
            <SpatialComparison
              key={g.account?.id ?? 'guest'}
              map={catalog.data.map}
              authenticated={!!g.account}
            />
          )}
          <h2>이 계산에 들어간 가정</h2>
          <ol className="assumption-list">
            {lab.model.assumptions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <h2>원화 예산과 시설 단가</h2>
          <p>
            총 예산 {won(lab.model.budget)}. 진주상평 산업단지 공개 사업계획의 참고 단가입니다. 해당
            지역의 실제 견적이 아닙니다.
          </p>
          <div className="placement-table">
            {(Object.keys(facilities) as FacilityType[]).map((t) => (
              <p key={t}>
                <b>{facilities[t].name}</b>
                <span>{won(lab.model.unitCosts[t])}/m²</span>
              </p>
            ))}
          </div>
          <p className="footnote">
            미포함: {lab.model.costModel.exclusions.join(' · ')}. 자료 공개연도 2022년, 단가
            기준연도·부가세 포함 여부 미확인. 서울 지역·현재 물가·시설 규격 차이 미보정.
          </p>
          <p className="footnote">
            <a href={lab.model.costModel.source?.url} target="_blank" rel="noreferrer">
              참고 단가 원문 · 12쪽 <ArrowUpRight size={12} />
            </a>
          </p>
          <h2>결과가 지나가는 검증</h2>
          <div className="evidence-checks">
            {[
              '고정 모델·관측 강우·배치 해시',
              '서버의 면적·시설·예산 검증',
              'SWMM 오류·비유한 값·물수지 검사',
              'API·CLI 일치와 시간간격 민감도 시험',
              '유출·침투·저류 분리와 재현 묶음',
            ].map((s) => (
              <p key={s}>
                <Check size={15} />
                {s}
              </p>
            ))}
          </div>
          <p className="footnote">
            출처:{' '}
            <a href={lab.model.rainfall.sourceUrl} target="_blank" rel="noreferrer">
              기상청 AWS
            </a>{' '}
            ·{' '}
            <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
              OpenStreetMap / ODbL
            </a>{' '}
            ·{' '}
            <a
              href="https://www.epa.gov/water-research/storm-water-management-model-swmm"
              target="_blank"
              rel="noreferrer"
            >
              EPA SWMM
            </a>
            <br />
            원본·변환·모델 버전은 다운로드와 연구 내보내기에 기록합니다. NOAA 수집자료는 누적 조건
            문제로 계산에서 제외했습니다.
          </p>
        </section>
      )}
      {auth && <AuthDialog onClose={() => setAuth(false)} onSuccess={g.setAccount} />}
    </div>
  );
}
