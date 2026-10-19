import { useState, type ReactNode } from 'react';
import { Layers3, Send, Wallet, X, MapPin, Trash2 } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { Budget } from '../../budget/dto/budgetDto';
import { BudgetEvidence } from '../../budget/view/BudgetEvidence';
import type { SharedInstallation } from '../../installation/entity/installation';
import { installationScore } from '../../installation/service/installationScore';
import type { HistoricalState } from '../../historical/controller/useHistorical';
import type { HistoricalDraft } from '../../historical/entity/historical';
import { HistoricalSubmissionPanel } from '../../historical/view/HistoricalSubmissionPanel';
import { facilities, won } from '../../game/service/gameService';
import { physicalAmount } from '../../physics/service/physicalValueFormat';

export function MapActionDock({
  historical,
  research: s,
  account,
  budget,
  remaining,
  ownInstallations,
  districts,
  onLogin,
  onInspect,
  onHistoricalInspect,
  children,
}: {
  historical: boolean;
  research: HistoricalState;
  account: Account | null;
  budget: Budget | null;
  remaining: number;
  ownInstallations: SharedInstallation[];
  districts: { id: string; name: string }[];
  onLogin: () => void;
  onInspect: (i: SharedInstallation) => void;
  onHistoricalInspect: (d: HistoricalDraft) => void;
  children: ReactNode;
}) {
  const [listOpen, setListOpen] = useState(false);
  const count = historical ? s.drafts.length : ownInstallations.length;
  const value = historical ? s.budget : budget;
  const balance = historical ? s.remaining : remaining;
  const limit = value?.policy.personalLimitKrw ?? 0;
  const finalLocked = !account && s.duration > 0 && s.elapsedSeconds >= s.duration;
  return (
    <div className="map-action-dock">
      <div className="map-dock-left">
        {historical && count === 0 && s.design.error && (
          <div className="dock-status" role="alert">
            {s.design.error}
            <button onClick={s.design.retry}>다시 시도</button>
          </div>
        )}
        {historical && count === 0 && account && s.design.guestCount > 0 && (
          <button
            className="installed-trigger"
            disabled={!s.design.ready}
            onClick={s.design.importGuest}
          >
            체험 설계 {s.design.guestCount}곳 가져오기
          </button>
        )}
        {count > 0 && (
          <div className="installed-dock">
            <button
              className="installed-trigger"
              aria-expanded={listOpen}
              onClick={() => setListOpen((v) => !v)}
            >
              <Layers3 size={17} /> 설치한 시설 보기 <b>{count}</b>
            </button>
            {listOpen && (
              <section
                className="dock-popover installed-list"
                aria-label="설치한 시설 목록"
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setListOpen(false);
                }}
              >
                <header>
                  <strong>내 설치 시설 · {count}곳</strong>
                  <button aria-label="설치한 시설 목록 닫기" onClick={() => setListOpen(false)}>
                    <X size={17} />
                  </button>
                </header>
                <div className="installed-list-scroll">
                  {historical
                    ? s.facilityStates.map(({ draft: d, before, score, state, requestError }) => (
                        <article key={d.marker.id}>
                          <button
                            className="installed-locate"
                            onClick={() => {
                              onHistoricalInspect(d);
                              setListOpen(false);
                            }}
                          >
                            <MapPin size={16} />
                            <span>
                              <strong>
                                {facilities[d.facilityType].name} · {d.site.name}
                              </strong>
                              <small>
                                {districts.find((r) => r.id === d.site.districtId)?.name} ·{' '}
                                {d.areaM2} m²{before ? ' · 설치 예정' : ''}
                              </small>
                              <b>
                                {finalLocked
                                  ? '최종 점수 · 로그인 후 확인'
                                  : before
                                    ? '설치 전'
                                    : score
                                      ? `누적 ${physicalAmount(score.differenceM3)} m³`
                                      : '누적 효과 계산 중'}
                              </b>
                            </span>
                          </button>
                          <button
                            className="installed-remove"
                            aria-label={`${d.site.name} 시설 취소`}
                            disabled={!s.design.ready}
                            onClick={() => s.remove(d.marker.id)}
                          >
                            <Trash2 size={15} />
                          </button>
                          {(requestError || ['FAILED', 'REJECTED'].includes(state ?? '')) && (
                            <button
                              onClick={() => void s.calculate(undefined, d.site.districtId)}
                              disabled={!s.design.ready || s.busy}
                            >
                              계산 실패 · 다시 시도
                            </button>
                          )}
                        </article>
                      ))
                    : ownInstallations.map((i) => (
                        <article key={i.id}>
                          <button
                            className="installed-locate"
                            onClick={() => {
                              onInspect(i);
                              setListOpen(false);
                            }}
                          >
                            <MapPin size={16} />
                            <span>
                              <strong>
                                {facilities[i.facilityType].name} · {i.cellId}
                              </strong>
                              <small>
                                {districts.find((d) => d.id === i.districtId)?.name} · {i.areaM2} m²
                              </small>
                              <b>{installationScore(i)}</b>
                            </span>
                          </button>
                        </article>
                      ))}
                </div>
                {historical && s.design.error && (
                  <p role="alert">
                    {s.design.error}
                    <button onClick={s.design.retry}>다시 시도</button>
                  </p>
                )}
                {historical && account && s.design.guestCount > 0 && (
                  <button disabled={!s.design.ready} onClick={s.design.importGuest}>
                    체험 설계 {s.design.guestCount}곳 가져오기
                  </button>
                )}
              </section>
            )}
          </div>
        )}
        <div className="map-dock-row">
          <div className="install-action">{children}</div>
          <div className="hover-help budget-dock" tabIndex={0} aria-label="전체 예산과 사용 내역">
            <Wallet size={17} />
            <div>
              <span>
                전체 예산 <b>{value ? won(limit) : '조회 중'}</b>
              </span>
              <div
                className="dock-budget-track"
                role="meter"
                aria-label="남은 예산"
                aria-valuemin={0}
                aria-valuemax={limit || 1}
                aria-valuenow={limit ? Math.max(0, Math.min(limit, balance)) : 0}
              >
                <i
                  style={{
                    width: `${limit ? Math.max(0, Math.min(100, (balance / limit) * 100)) : 0}%`,
                  }}
                />
              </div>
              <small>잔액 {value ? won(balance) : '—'}</small>
            </div>
            <section className="dock-popover" aria-label="예산 상세">
              <h3>전체 예산 {value ? won(limit) : '조회 중'}</h3>
              <p>
                사용 {value ? won(limit - balance) : '—'} · 잔액 {value ? won(balance) : '—'}
              </p>
              <BudgetEvidence
                value={value}
                research={historical}
                accounting={historical ? s.accounting : undefined}
              />
            </section>
          </div>
        </div>
      </div>
      {historical && (
        <div
          className={`hover-help submission-dock${s.submission.error ? ' has-error' : ''}`}
          tabIndex={0}
        >
          <button
            className="submit-action"
            disabled={!count || !s.design.ready || s.submission.busy || count > 50}
            onClick={() => (account ? void s.submit() : onLogin())}
          >
            <Send size={19} />
            {s.submission.busy ? '제출 중' : account ? '제출하기' : '로그인 후 제출하기'}
          </button>
          <div className="dock-popover">
            <HistoricalSubmissionPanel
              submission={s.submission}
              draftCount={count}
              submit={s.submit}
              authenticated={!!account}
              onLogin={onLogin}
              designReady={s.design.ready}
              designRevision={s.design.revision}
              onReloadDesign={s.design.reload}
              showAction={false}
            />
          </div>
        </div>
      )}
    </div>
  );
}
