import { lazy, Suspense, useState, useEffect } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  MapPin,
  CloudRain,
  Layers3,
  RotateCcw,
  Scan,
  Box,
  Plus,
  Undo2,
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
  ShieldCheck,
  Database,
} from 'lucide-react';
import { useGame } from '../controller/useGame';
import { useCatalog } from '../../catalog/controller/useCatalog';
import type { FacilityType } from '../entity/game';
import { facilities, format, won, totalCost } from '../service/gameService';
import * as repo from '../repository/gameRepository';
import { logout } from '../../account/repository/accountRepository';
import { ApprovalPage } from '../../administration/view/ApprovalPage';
import { memberTypeNames } from '../../account/entity/account';
import { AuthDialog } from '../../account/view/AuthDialog';
import { Hydrograph } from './Hydrograph';
import { Leaderboard } from './Leaderboard';
import { ResearchPage } from '../../research/view/ResearchPage';
import { SpatialComparison } from '../../spatial/view/SpatialComparison';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
const MapScene = lazy(() => import('../../catalog/view/MapScene'));
const icons = { RAIN_GARDEN: Leaf, PERMEABLE_PAVEMENT: Grid2X2, GREEN_ROOF: House };
export function GamePage() {
  const g = useGame();
  const catalog = useCatalog();
  const [tab, setTab] = useState<'studio' | 'leaderboard' | 'research' | 'data' | 'admin'>(
    'studio'
  );
  const [selected, setSelected] = useState<string | null>(null),
    [type, setType] = useState<FacilityType>('RAIN_GARDEN'),
    [area, setArea] = useState(40);
  const [auth, setAuth] = useState(false),
    [top, setTop] = useState(false),
    [reset, setReset] = useState(0),
    [showList, setShowList] = useState(false),
    [showSaves, setShowSaves] = useState(false);
  useEffect(() => {
    if (g.account?.role === 'ADMIN') setTab('admin');
    else setTab((t) => (t === 'admin' ? 'studio' : t));
  }, [g.account?.id, g.account?.role]);
  const lab = g.lab;
  const cell = lab?.model.cells.find((c) => c.id === selected);
  const placement = g.placements.find((p) => p.cellId === selected);
  const cost = lab ? totalCost(lab, g.placements) : 0;
  function select(id: string | null) {
    const c = lab?.model.cells.find((c) => c.id === id || c.buildingId === id);
    setSelected(c?.id ?? null);
    if (c) {
      const p = g.placements.find((p) => p.cellId === c.id);
      setType(p?.facilityType ?? c.allowedTypes[0]);
      setArea(p?.areaM2 ?? Math.min(40, c.maxAreaM2));
    }
  }
  const result = g.job?.result;
  const working = g.busy || g.job?.state === 'QUEUED' || g.job?.state === 'RUNNING';
  return (
    <div className="game-shell">
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
                ['studio', '설계실'],
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
      {!lab ? (
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
      ) : tab === 'studio' ? (
        <div className="studio-layout">
          <aside className="mission-panel">
            <div className="eyebrow">
              SEONGSU CHALLENGE <span>01</span>
            </div>
            <h1>
              도시의 빈틈에,
              <br />
              빗물이 머물 자리.
            </h1>
            <p className="mission-intro">
              시설을 배치하고, 실제로 내린 비가
              <br />
              어떻게 달라지는지 계산해 보세요.
            </p>
            <div className="location">
              <MapPin size={13} /> 서울 성동구 · 연무장길 일대
            </div>
            <div className="mission-map" aria-hidden="true">
              <svg viewBox="-155 -160 310 320">
                {catalog.data?.map.buildings.map((b) => (
                  <polygon
                    key={b.id}
                    points={b.coordinates.map(([x, y]) => `${x},${-y}`).join(' ')}
                  />
                ))}
              </svg>
              <span>
                REAL FOOTPRINTS
                <br />
                37.54425° N · 127.05400° E
              </span>
            </div>
            <div className="mission-rain">
              <CloudRain size={22} />
              <div>
                <b>2024. 07. 18.</b>
                <span>서울 108 관측소 · 1분 자료</span>
              </div>
              <strong>
                {lab.model.rainfall.totalDepthMm}
                <small>mm</small>
              </strong>
            </div>
            <div className="section-label">
              실험 조건 <span>고정</span>
            </div>
            <dl className="mission-facts">
              <div>
                <dt>계산 엔진</dt>
                <dd>EPA SWMM 5.2.4</dd>
              </div>
              <div>
                <dt>실험 단위</dt>
                <dd>{lab.model.cells.length}개 표면</dd>
              </div>
              <div>
                <dt>설계 예산</dt>
                <dd>{won(lab.model.budget)}</dd>
              </div>
              <div>
                <dt>평가 대상</dt>
                <dd>유출·잔여저류 총량</dd>
              </div>
            </dl>
            <div className="scope-badge">
              <ShieldCheck size={18} />
              <div>
                <b>탐색 모델 · EXPLORATORY</b>
                <p>
                  지형·관망·현장 보정 전.
                  <br />
                  실제 침수나 공사 효과를 예측하지 않습니다.
                </p>
              </div>
            </div>
            <button className="text-button" onClick={() => setTab('data')}>
              자료와 가정 확인 <ArrowRight size={14} />
            </button>
            <a
              className="source-credit"
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noreferrer"
            >
              © OpenStreetMap contributors <ArrowUpRight size={12} />
            </a>
          </aside>
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
            <div className="compact-model-context">
              <b>성수 · 탐색 모델</b>
              <span>2024.07.18 · 실측 {lab.model.rainfall.totalDepthMm} mm</span>
              <p>지형·관망·토양 미검증. 실제 침수·공사 효과 예측 불가.</p>
              <button className="text-button" onClick={() => setTab('data')}>
                자료와 가정 확인 <ArrowUpRight size={13} />
              </button>
            </div>
            <section className="design-stage" aria-label="시설 배치 3D 지도">
              <div className="scene-overline">
                <span>
                  <i />
                  공개 건물 경계
                </span>
                <span>표고 평탄화 · 설치 가능성 가정</span>
              </div>
              {catalog.error ? (
                <div className="empty-state">
                  <p>{catalog.error}</p>
                  <button onClick={catalog.retry}>다시 시도</button>
                </div>
              ) : catalog.data ? (
                <ErrorBoundary
                  fallback={
                    <div className="empty-state">
                      <p>3D 표시를 사용할 수 없습니다. 아래 목록에서 시설을 선택할 수 있습니다.</p>
                      <button onClick={() => setShowList(true)}>구역 목록 열기</button>
                    </div>
                  }
                >
                  <Suspense fallback={<div className="empty-state">3D 장면 구성 중</div>}>
                    <MapScene
                      map={catalog.data.map}
                      selected={cell?.buildingId ?? null}
                      onSelect={select}
                      topView={top}
                      reset={reset}
                      cells={lab.model.cells}
                      placements={g.placements}
                      selectedCell={selected}
                      onCellSelect={select}
                    />
                  </Suspense>
                </ErrorBoundary>
              ) : (
                <div className="empty-state">실제 건물 경계 불러오는 중</div>
              )}
              <div className="scene-labels">
                <b>
                  SEONGSU
                  <br />
                  <span>RAIN LAB</span>
                </b>
                <small>
                  회전 · 드래그
                  <br />
                  확대 · 스크롤
                </small>
              </div>
              <div className="scene-controls">
                <button
                  aria-label={top ? '입체 보기' : '위에서 보기'}
                  aria-pressed={top}
                  onClick={() => setTop((v) => !v)}
                >
                  {top ? <Box size={18} /> : <Scan size={18} />}
                </button>
                <button aria-label="시점 초기화" onClick={() => setReset((v) => v + 1)}>
                  <RotateCcw size={17} />
                </button>
                <button
                  aria-label="구역 목록"
                  aria-pressed={showList}
                  onClick={() => setShowList((v) => !v)}
                >
                  <Menu size={18} />
                </button>
              </div>
              {showList && (
                <div className="cell-list">
                  <b>실험 구역 선택</b>
                  {lab.model.cells.map((c) => (
                    <button
                      key={c.id}
                      className={c.id === selected ? 'selected' : ''}
                      onClick={() => select(c.id)}
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
                {(Object.keys(facilities) as FacilityType[]).map((t) => {
                  const Icon = icons[t];
                  return (
                    <button
                      key={t}
                      className={type === t ? 'selected' : ''}
                      onClick={() => {
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
                  className="undo-button"
                  aria-label="마지막 배치 변경 되돌리기"
                  disabled={!g.canUndo}
                  onClick={g.undo}
                >
                  <Undo2 size={18} />
                </button>
              </div>
            </section>
            <Hydrograph job={g.job} rainfall={lab.model.rainfall} />
            <div className="studio-footnote">
              <span>
                <i />
                실측 강우 · 명시적 가정 · 서버 계산
              </span>
              <span>3D 물 표현은 침수 결과를 의미하지 않음</span>
            </div>
          </main>
          <aside className="inspector">
            <div className="inspector-top">
              <span className="eyebrow">{cell ? 'DESIGN A SURFACE' : 'YOUR DESIGN'}</span>
              <Layers3 size={17} />
            </div>
            <h2>{cell ? cell.name : '빗물의 다음 목적지'}</h2>
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
                <div className="facility-options">
                  {cell.allowedTypes.map((t) => {
                    const Icon = icons[t];
                    return (
                      <button
                        key={t}
                        className={type === t ? 'active' : ''}
                        onClick={() => setType(t)}
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
                      type="number"
                      min="1"
                      max={cell.maxAreaM2}
                      step="0.01"
                      value={area}
                      onChange={(e) => setArea(Number(e.target.value))}
                    />{' '}
                    m²
                  </span>
                </label>
                <input
                  className="area-slider"
                  aria-label="설치 면적 조절"
                  type="range"
                  min="1"
                  max={cell.maxAreaM2}
                  step="1"
                  value={area}
                  onChange={(e) => setArea(Number(e.target.value))}
                />
                <div className="area-range">
                  <span>1 m²</span>
                  <span>최대 {format.format(cell.maxAreaM2)} m²</span>
                </div>
                <div className="placement-cost">
                  <span>추정 설치비</span>
                  <strong>{won(area * lab.model.unitCosts[type])}</strong>
                </div>
                <button
                  className="primary-button"
                  disabled={
                    g.busy ||
                    !Number.isFinite(area) ||
                    area <= 0 ||
                    area > cell.maxAreaM2 ||
                    !cell.allowedTypes.includes(type) ||
                    cost -
                      (placement
                        ? placement.areaM2 * lab.model.unitCosts[placement.facilityType]
                        : 0) +
                      area * lab.model.unitCosts[type] >
                      lab.model.budget
                  }
                  onClick={() =>
                    g.change([
                      ...g.placements.filter((p) => p.cellId !== cell.id),
                      { cellId: cell.id, facilityType: type, areaM2: Math.round(area * 100) / 100 },
                    ])
                  }
                >
                  {placement ? '배치 변경' : '이 구역에 배치'}
                  <Plus size={16} />
                </button>
                {placement && (
                  <button
                    className="text-button remove-button"
                    onClick={() => g.change(g.placements.filter((p) => p.cellId !== cell.id))}
                  >
                    <Trash2 size={14} />이 시설 제거
                  </button>
                )}
              </>
            ) : (
              <div className="intro-steps">
                <div>
                  <span>01</span>
                  <p>
                    시설을 고르고
                    <br />
                    <b>설치할 구역을 선택</b>
                  </p>
                </div>
                <div>
                  <span>02</span>
                  <p>
                    면적과 예산을 맞춰
                    <br />
                    <b>나만의 배치 완성</b>
                  </p>
                </div>
                <div>
                  <span>03</span>
                  <p>
                    같은 강우로 계산하고
                    <br />
                    <b>다른 설계와 기록 비교</b>
                  </p>
                </div>
              </div>
            )}
            <div className="budget-box">
              <div>
                <span>추정 비용</span>
                <b>
                  {won(cost)}
                  <small> / {won(lab.model.budget)}</small>
                </b>
              </div>
              <div className="budget-track">
                <i style={{ width: Math.min(100, (cost / lab.model.budget) * 100) + '%' }} />
              </div>
              <span>{g.placements.length}개 시설 · 공개계획 참고 단가 · 부대비용 별도</span>
            </div>
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
            <button
              className="simulate-button"
              disabled={working || !lab.model.simulationAvailable}
              onClick={() => (g.account ? void g.run() : setAuth(true))}
            >
              <Play size={17} />
              {working
                ? g.job?.state === 'QUEUED'
                  ? '계산 순서 대기'
                  : '서버에서 계산 중'
                : '강우 시뮬레이션'}
              <ArrowRight size={16} />
            </button>
            {g.job?.state === 'FAILED' || g.job?.state === 'REJECTED' ? (
              <p className="form-error" role="alert">
                계산이 품질 검사를 통과하지 못했습니다. 코드: {g.job.errorCode}
              </p>
            ) : null}
            {result && (
              <div className="result-card">
                <div>
                  <span>계산한 설계의 탐색 점수</span>
                  <strong>
                    {format.format(result.score)}
                    <small>점</small>
                  </strong>
                </div>
                <dl>
                  <div>
                    <dt>기간 유출</dt>
                    <dd>{format.format(result.strategy.runoffM3)} m³</dd>
                  </div>
                  <div>
                    <dt>최종 잔여저류</dt>
                    <dd>{format.format(result.strategy.finalStorageM3)} m³</dd>
                  </div>
                  <div>
                    <dt>물수지 오차</dt>
                    <dd>{format.format(result.strategy.runoffContinuityPercent)}%</dd>
                  </div>
                  <div>
                    <dt>가정 변화 점수 범위</dt>
                    <dd>
                      {format.format(
                        Math.min(result.score, ...result.sensitivity.map((s) => s.score))
                      )}{' '}
                      ~{' '}
                      {format.format(
                        Math.max(result.score, ...result.sensitivity.map((s) => s.score))
                      )}
                    </dd>
                  </div>
                </dl>
                <p>
                  현재 편집 중인 배치와 다를 수 있습니다. 계산한 버전의 결과입니다. 범위는 투수계수
                  가정 비교이며 신뢰구간이 아닙니다.
                </p>
                <button
                  className="outline-button"
                  disabled={g.busy}
                  onClick={() =>
                    void g.action(async () => {
                      await repo.submit(g.job!.id);
                      g.setNotice('탐색 기록 제출 완료');
                    })
                  }
                >
                  <Trophy size={15} />
                  탐색 기록 제출
                </button>
                <a className="text-button" href={`/api/v1/simulations/${g.job?.id}/bundle`}>
                  <Download size={14} />
                  입력·결과 재현 묶음
                </a>
              </div>
            )}
          </aside>
        </div>
      ) : tab === 'leaderboard' ? (
        <Leaderboard />
      ) : tab === 'research' ? (
        <ResearchPage
          account={g.account}
          lab={lab}
          onReplay={(p) => {
            g.newDesign();
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
              <h2>기상청 서울 분강우</h2>
              <strong>
                {lab.model.rainfall.totalDepthMm}
                <small> mm</small>
              </strong>
              <p>
                2024.07.18 05:00~23:59 KST. 1,140개 누적 관측에서 1,139분 깊이 추출. 결측·음수·자정
                경계 검사와 이동누적 교차 확인.
              </p>
              <a href="/data/kma-event.json" download>
                관측 파생자료 <Download size={14} />
              </a>
            </article>
            <article>
              <Database />
              <span className="state done">공개 공간자료</span>
              <h2>성수동 실제 건물 경계</h2>
              <strong>
                {catalog.data?.map.buildings.length ?? '—'}
                <small>개</small>
              </strong>
              <p>
                OpenStreetMap 형상. 높이 일부는 시각화 가정입니다. 선택 옥상 면적은 WGS84 타원체
                계산, 지상 구역은 가정 실험 단위입니다.
              </p>
              <a href="/data/seongsu.json" download>
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
            총 예산 {won(lab.model.budget)}. 진주상평 산업단지 공개 사업계획의 참고 단가입니다.
            성수동 실제 견적이 아닙니다.
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
