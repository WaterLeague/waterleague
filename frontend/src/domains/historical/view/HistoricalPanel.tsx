import { HistoricalInstallationTrack } from './HistoricalInstallationTrack';
import { HistoricalSubmissionPanel } from './HistoricalSubmissionPanel';
import { InitializationEvidence } from '../../physics/view/InitializationEvidence';
import { InitializationSensitivityEvidence } from '../../physics/view/InitializationSensitivityEvidence';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
import { FacilityProfileEvidence } from '../../facility/view/FacilityProfileEvidence';
import type { ReactNode } from 'react';
import {
  Play,
  Pause,
  SlidersHorizontal,
  Trash2,
  Leaf,
  Grid2X2,
  House,
  Waves,
  Sprout,
  Route,
} from 'lucide-react';
import type { HistoricalState } from '../controller/useHistorical';
import type { SharedSite } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities, format } from '../../game/service/gameService';
import type { HistoricalDraft } from '../entity/historical';
import './historical.css';
import { FacilityPlacementPanel } from '../../installation/view/FacilityPlacementPanel';
import { CostRecordEvidence } from '../../cost/view/CostRecordEvidence';
import { RunoffComparison } from '../../physics/view/RunoffComparison';
const time = (s: string) =>
  new Date(s).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
    timeZone: 'Asia/Seoul',
  });
const icons = {
  RAIN_GARDEN: Leaf,
  PERMEABLE_PAVEMENT: Grid2X2,
  GREEN_ROOF: House,
  BIORETENTION: Sprout,
  VEGETATIVE_SWALE: Waves,
  INFILTRATION_TRENCH: Route,
};
const clockTime = new Intl.DateTimeFormat('ko-KR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
  timeZone: 'Asia/Seoul',
});
export function HistoricalPlayback({ state: s }: { state: HistoricalState }) {
  if (!s.frameCount) return null;
  return (
    <div className="historical-playback" role="group" aria-label="재해 재생 상태">
      <button
        className="historical-play-toggle"
        aria-label={s.playing ? '재해 일시정지' : '재해 재생'}
        onClick={() => s.setPlaying((v) => !v)}
      >
        {s.playing ? <Pause size={16} /> : <Play size={16} />}
      </button>
      <time dateTime={s.at ?? undefined}>
        {s.at && clockTime.format(new Date(s.at))} <small>KST</small>
      </time>
      <strong>{s.selectedRain ? `1분 ${format.format(s.rainMm)} mm` : '강우 자료 없음'}</strong>
    </div>
  );
}
export function HistoricalTimeline({
  state: s,
  onInspect,
  children,
}: {
  state: HistoricalState;
  onInspect: (draft: HistoricalDraft) => void;
  children?: ReactNode;
}) {
  const markers = (s.event && s.duration > 0 ? [...s.drafts] : []).sort(
    (a, b) => Date.parse(a.marker.installedAt) - Date.parse(b.marker.installedAt)
  );
  return (
    <section className="historical-timeline" aria-label="재해 시간 재생">
      {s.frameCount > 0 && (
        <>
          <HistoricalInstallationTrack
            drafts={s.drafts}
            start={s.event?.regions[0]?.start}
            duration={s.duration}
            elapsed={s.elapsedSeconds}
            onSelect={(draft, seconds) => {
              s.setElapsedSeconds(seconds);
              s.setPlaying(false);
              onInspect(draft);
            }}
          >
            <input
              type="range"
              aria-label="재해 재생 시각"
              aria-valuetext={s.at ? `${time(s.at)} KST` : undefined}
              min="0"
              max={s.duration}
              value={s.elapsedSeconds}
              onChange={(e) => {
                s.setElapsedSeconds(Number(e.target.value));
                s.setPlaying(false);
              }}
            />
          </HistoricalInstallationTrack>
          <select
            aria-label="재해 재생 속도"
            value={s.speed}
            onChange={(e) => s.setSpeed(Number(e.target.value))}
          >
            {[1, 2, 3, 5, 10, 60, 240, 900, 3600].map((v) => (
              <option key={v} value={v}>
                {v}배속
              </option>
            ))}
          </select>
        </>
      )}
      <details className="historical-playback-tools">
        <summary>
          <SlidersHorizontal size={15} /> 재생 도구
        </summary>
        <div>
          {s.frameCount > 0 && (
            <div className="historical-jumps">
              <button
                onClick={() => {
                  s.setIndex(
                    Math.max(
                      0,
                      (s.selectedRain ?? s.event!.regions[0]).depthsMm.findIndex((v) => v > 0)
                    )
                  );
                  s.setPlaying(true);
                }}
              >
                첫 비
              </button>
              <button
                onClick={() => {
                  const rain = (s.selectedRain ?? s.event!.regions[0]).depthsMm;
                  s.setIndex(rain.indexOf(Math.max(...rain)));
                  s.setPlaying(false);
                }}
              >
                강우 최대
              </button>
            </div>
          )}
          {!!markers.length && (
            <div className="historical-installation-times" aria-label="설치 시각 목록">
              {markers.map((draft) => {
                const Icon = icons[draft.facilityType];
                return (
                  <button
                    key={draft.marker.id}
                    onClick={() => {
                      s.setElapsedSeconds(
                        (Date.parse(draft.marker.installedAt) -
                          Date.parse(s.event!.regions[0].start)) /
                          1000
                      );
                      s.setPlaying(false);
                      onInspect(draft);
                    }}
                  >
                    <Icon size={17} />
                    <span>
                      {facilities[draft.facilityType].name} · {draft.site.name}
                      <time dateTime={draft.marker.installedAt}>
                        {time(draft.marker.installedAt)} KST
                      </time>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          {children}
          {s.event && !s.selectedRain && (
            <p role="status">
              선택한 구의 이 사건 관측자료를 확보하지 못했습니다. 다른 지역의 값을 대신 표시하지
              않습니다.
            </p>
          )}
          {s.event && (
            <details className="historical-event-note">
              <summary>사건 자료·계산 조건</summary>
              <p>{s.event.summary}</p>
              <a href={s.event.evidenceUrl} target="_blank" rel="noreferrer">
                {s.event.evidenceTitle} ↗
              </a>
              <p>
                {s.selectedRain &&
                  `${s.selectedRain.stationName} AWS · 대표 지점에서 ${s.selectedRain.distanceKm}km · 관측 창 누적 ${s.selectedRain.totalDepthMm}mm`}
              </p>
              <p>
                현재 공개 지형에 당시 강우 적용 · 당시 침수 피해 복원 아님 · 구별 강우에 따라 빗줄기
                표시
              </p>
            </details>
          )}
        </div>
      </details>
    </section>
  );
}
export function HistoricalPanel({
  onClose,
  state: s,
  site,
  type,
  area,
  onType,
  onArea,
  onLogin,
  authenticated,
  error,
  districtName,
  districts = [],
  onInspect,
}: {
  state: HistoricalState;
  onClose?: () => void;
  site: SharedSite | null;
  type: FacilityType | '';
  area: string;
  onType: (t: FacilityType) => void;
  onArea: (a: string) => void;
  onLogin: () => void;
  authenticated: boolean;
  error: string;
  districtName: string;
  districts?: { id: string; name: string }[];
  onInspect: (draft: HistoricalDraft) => void;
}) {
  const placed = s.drafts.find(
    (d) => d.site.districtId === site?.districtId && d.site.cellId === site?.cellId
  );
  const working =
    !s.calculationsReady || s.busy || s.job?.state === 'QUEUED' || s.job?.state === 'RUNNING';
  const finalLocked = !authenticated && s.duration > 0 && s.elapsedSeconds >= s.duration;
  return (
    <FacilityPlacementPanel
      onClose={onClose}
      site={site}
      type={type}
      area={area}
      onType={onType}
      onArea={onArea}
      districtName={districtName}
      context="개인 재해 실험"
      research
      budget={s.budget}
      budgetAccounting={s.accounting}
      remaining={s.remaining}
      limit={s.budget?.policy.personalLimitKrw ?? 0}
      budgetReady={!!s.budget}
      busy={!s.design.ready}
      canInstall={s.design.ready && s.drafts.length < 50 && s.elapsedSeconds < s.duration}
      readOnlyMessage={
        !s.design.ready
          ? '설계 저장·복원을 확인해 주세요.'
          : s.elapsedSeconds >= s.duration
            ? '재해 종료 이전 시각으로 이동해 설치하세요.'
            : '재해 실험 배치 50곳을 모두 사용했습니다.'
      }
      onInstall={() => {
        if (site && type) s.add(site, type, Number(area));
      }}
      occupied={
        placed
          ? {
              ...placed.marker,
              planned: !!s.at && Date.parse(s.at) < Date.parse(placed.marker.installedAt),
              onRemove: () => s.remove(placed.marker.id),
            }
          : undefined
      }
      error={error || s.error || s.job?.message}
    >
      <div className="historical-design-sync" aria-label="재해 설계 저장">
        <strong>
          {authenticated
            ? s.design.saving
              ? '설계 저장 중'
              : s.design.loading
                ? '저장된 설계 확인 중'
                : '설계 저장됨'
            : '게스트 플레이 · 제출할 때 로그인'}
        </strong>
        {authenticated ? (
          <small>설치·취소 시 저장 · 다시 접속해 이어서 실험</small>
        ) : (
          <small>체험 설계는 이 화면에서만 유지됩니다.</small>
        )}
        {s.design.error && (
          <p role="alert">
            {s.design.error}{' '}
            <button onClick={s.design.retry}>
              {s.design.conflict ? '저장된 설계 불러오기' : '다시 시도'}
            </button>
          </p>
        )}
        {authenticated && s.design.guestCount > 0 && (
          <button disabled={!s.design.ready} onClick={s.design.importGuest}>
            체험 설계 {s.design.guestCount}곳 가져오기
          </button>
        )}
      </div>
      <div className="historical-design-summary">
        <strong>전체 실험 시설 · {s.drafts.length}곳</strong>
        {s.facilityStates.map(({ draft: d, before, score, state, requestError }) => {
          return (
            <div key={d.marker.id}>
              <span>
                <button onClick={() => onInspect(d)}>
                  {facilities[d.facilityType].name} · {d.site.name}
                </button>{' '}
                · {d.areaM2}m²
                <small>
                  {districts.find((r) => r.id === d.site.districtId)?.name ?? d.site.districtId} ·{' '}
                  {time(d.marker.installedAt)} 설치{before ? ' 예정' : ''}
                </small>
                <small>
                  {finalLocked ? (
                    '최종 점수 · 로그인 후 확인'
                  ) : before ? (
                    '설치 전 · 누적 0 m³'
                  ) : score ? (
                    `누적 ${physicalAmount(score.differenceM3)} m³ · ${time(score.at)}까지`
                  ) : requestError || ['FAILED', 'REJECTED'].includes(state ?? '') ? (
                    <button
                      onClick={() => void s.calculate(undefined, d.site.districtId)}
                      disabled={!s.design.ready || !s.calculationsReady || s.busy}
                    >
                      계산 실패 · 이 구 다시 계산
                    </button>
                  ) : (
                    '누적 효과 계산 중'
                  )}
                </small>
              </span>
              <button
                aria-label={d.site.name + ' 시설 취소'}
                disabled={!s.design.ready}
                onClick={() => s.remove(d.marker.id)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          );
        })}
      </div>
      <button
        className="solid-button"
        disabled={!s.design.ready || working || !s.current.length || !s.lab}
        onClick={() => void s.calculate()}
      >
        {working
          ? '설치 이후 효과 계산 중'
          : s.currentResult
            ? '같은 설계 다시 계산'
            : '설치 이후 효과 계산'}
      </button>

      {authenticated && placed?.site.initializationPolicy && (
        <div className="historical-sensitivity-action">
          <button
            className="outline-button"
            disabled={!s.design.ready || working || !s.lab}
            onClick={() => void s.calculate(placed.site.cellId)}
          >
            {placed.facilityType === 'VEGETATIVE_SWALE'
              ? '이 수로의 선행 상태 확인'
              : '이 시설의 시작 수분 비교'}
          </button>
          <p>
            {placed.facilityType === 'VEGETATIVE_SWALE'
              ? '식생수로의 선행 관측 이후 상태를 확인합니다. 초기 포화도는 적용되지 않아 건습 비교를 제공하지 않습니다.'
              : '선택 시설 한 곳의 건조·포화 시작 조건을 추가 계산합니다. 일반 계산보다 시간이 더 걸립니다.'}
          </p>
        </div>
      )}
      <HistoricalSubmissionPanel
        submission={s.submission}
        draftCount={s.drafts.length}
        submit={s.submit}
        authenticated={authenticated}
        onLogin={onLogin}
        designReady={s.design.ready}
        designRevision={s.design.revision}
        onReloadDesign={s.design.reload}
      />
      {finalLocked && (
        <section className="historical-result" aria-label="최종 점수 로그인 안내">
          <h3>재해 체험 종료</h3>
          <p>설치와 진행 점수는 체험할 수 있습니다. 제출과 최종 점수 확인은 로그인이 필요합니다.</p>
          <button className="solid-button" onClick={onLogin}>
            로그인하고 최종 점수 확인
          </button>
        </section>
      )}
      {s.currentResult && !finalLocked && (
        <section className="historical-result" aria-label="과거 강우 비교 결과">
          <h3>재생 시각까지 누적 효과</h3>
          {authenticated && (
            <a className="text-button" href={`/api/v1/historical/${s.job!.id}/bundle`}>
              재현 자료 다운로드
            </a>
          )}
          <strong data-effect={(s.currentScore?.differenceM3 ?? 0) < 0 ? 'increase' : 'decrease'}>
            {s.currentScore
              ? `${physicalAmount(s.currentScore.differenceM3)} m³`
              : '누적 기록 없음'}
          </strong>
          <p>시설 없는 조건 대비 평가체적 감소</p>
          {s.currentScore && <p>{time(s.currentScore.at)}까지 · 분 종료 기록 · 미래 결과 제외</p>}
          {(s.currentScore?.differenceM3 ?? 0) < 0 && <p>음수는 평가체적 증가를 뜻합니다.</p>}
          <dl>
            <dt>시설 없음</dt>
            <dd>{s.currentScore ? physicalAmount(s.currentScore.baselineAccountedM3) : '—'}m³</dd>
            <dt>내 실험 설계</dt>
            <dd>{s.currentScore ? physicalAmount(s.currentScore.designAccountedM3) : '—'}m³</dd>
          </dl>
          <p>
            선택한 표면의 유출·배수·순저류 합 비교입니다. 구 전체 유출량이나 실제 침수 예측이
            아닙니다.
          </p>
          <p>작은 차이는 물수지 오차보다 작을 수 있습니다. 현장 효과로 확정하지 않습니다.</p>
          {s.currentResult.initializationSensitivity && (
            <details>
              <summary>사건 전체 창의 시작 수분 비교 · 누적 효과와 별도</summary>
              <InitializationSensitivityEvidence
                value={s.currentResult.initializationSensitivity}
              />
            </details>
          )}
          {s.currentResult.facilities
            ?.filter((f) => !site || f.cellId === site.cellId)
            .map(
              (f) =>
                f.runoffComparison && (
                  <details key={f.cellId}>
                    <summary>{f.cellId} · 설치부터 종료까지 전체 계산 상세</summary>
                    <RunoffComparison value={f.runoffComparison} />
                  </details>
                )
            )}
          <details>
            <summary>계산 조건</summary>
            {s.currentResult.facilities
              ?.filter((f) => !site || f.cellId === site.cellId)
              .map(
                (f) =>
                  (f.initialization || f.facilityDesign || f.costRecord) && (
                    <details key={f.cellId}>
                      <summary>{f.cellId} · 시작 수분·시설 제원</summary>
                      {f.initialization && <InitializationEvidence value={f.initialization} />}
                      {f.facilityDesign && <FacilityProfileEvidence {...f.facilityDesign} />}
                      {f.costRecord && <CostRecordEvidence value={f.costRecord} />}
                    </details>
                  )
              )}
            {s.currentResult.assumptions.map((v) => (
              <p key={v}>{v}</p>
            ))}
            <p>EPA SWMM {s.currentResult.engineVersion} · 현장 보정 전</p>
          </details>
        </section>
      )}
    </FacilityPlacementPanel>
  );
}
