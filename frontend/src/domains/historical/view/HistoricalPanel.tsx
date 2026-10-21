import { facilityIcons } from '../../facility/view/facilityIcons';
import { GameSelect } from '../../../shared/ui/GameSelect';
import { HistoricalInstallationTrack } from './HistoricalInstallationTrack';
import { InitializationEvidence } from '../../physics/view/InitializationEvidence';
import { InitializationSensitivityEvidence } from '../../physics/view/InitializationSensitivityEvidence';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
import { FacilityProfileEvidence } from '../../facility/view/FacilityProfileEvidence';
import { PavementMaintenanceEvidence } from '../../facility/view/PavementMaintenanceEvidence';
import { useMemo, type ReactNode } from 'react';
import { Play, Pause, SlidersHorizontal } from 'lucide-react';
import type { HistoricalState } from '../controller/useHistorical';
import type { SharedSite } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities } from '../../game/service/gameService';
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
    </div>
  );
}
export function HistoricalTimeline({
  state: s,
  districtId = '',
  onInspect,
  children,
}: {
  state: HistoricalState;
  districtId?: string;
  onInspect: (draft: HistoricalDraft) => void;
  children?: ReactNode;
}) {
  const selectedRain = s.event?.regions.find((r) => r.districtId === districtId);
  const rain = useMemo(() => {
    if (districtId) return selectedRain?.depthsMm ?? [];
    const regions = s.event?.regions ?? [];
    // 전체 보기의 탐색은 실제 구별 관측 중 최댓값이 있는 분으로 이동한다.
    return (regions[0]?.depthsMm ?? []).map((_, i) =>
      Math.max(...regions.map((r) => r.depthsMm[i] ?? 0))
    );
  }, [s.event, districtId, selectedRain]);
  const markers = (s.event && s.duration > 0 ? [...s.drafts] : []).sort(
    (a, b) => Date.parse(a.marker.installedAt) - Date.parse(b.marker.installedAt)
  );
  return (
    <section className="historical-timeline" aria-label="재해 시간 재생">
      {s.frameCount > 0 && (
        <>
          <HistoricalPlayback state={s} />
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
          <GameSelect
            label="재해 재생 속도"
            value={String(s.speed)}
            onChange={(v) => s.setSpeed(Number(v))}
            options={[1, 2, 3, 5, 10, 60, 240, 900, 3600].map((v) => ({
              value: String(v),
              label: `${v}배속`,
            }))}
          />
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
                disabled={!rain.length}
                onClick={() => {
                  s.setIndex(
                    Math.max(
                      0,
                      rain.findIndex((v) => v > 0)
                    )
                  );
                  s.setPlaying(true);
                }}
              >
                첫 비
              </button>
              <button
                disabled={!rain.length}
                onClick={() => {
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
                const Icon = facilityIcons[draft.facilityType];
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
          {s.event && districtId && !selectedRain && (
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
                {selectedRain &&
                  `${selectedRain.stationName} AWS · 대표 지점에서 ${selectedRain.distanceKm}km · 관측 창 누적 ${selectedRain.totalDepthMm}mm`}
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
  onInstalled,
  canInstall = true,
  onClose,
  state: s,
  site,
  type,
  area,
  onType,
  onArea,
  authenticated,
  error,
  districtName,
}: {
  state: HistoricalState;
  onInstalled?: (site: SharedSite) => void;
  canInstall?: boolean;
  onClose?: () => void;
  site: SharedSite | null;
  type: FacilityType | '';
  area: string;
  onType: (t: FacilityType) => void;
  onArea: (a: string) => void;
  authenticated: boolean;
  error: string;
  districtName: string;
}) {
  const placed = s.drafts.find(
    (d) => d.site.districtId === site?.districtId && d.site.cellId === site?.cellId
  );
  const selected = s.facilityStates.find((value) => value.draft.marker.id === placed?.marker.id);
  const result = selected?.result;
  const calculation = selected?.calculation;
  const score = selected?.before ? null : selected?.score;
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
        if (canInstall && site && type && s.add(site, type, Number(area))) onInstalled?.(site);
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
      {authenticated && placed?.site.initializationPolicy && (
        <div className="historical-sensitivity-action">
          <button
            className="outline-button"
            disabled={!s.design.ready || working || !s.selectedRain}
            onClick={() => void s.calculate(placed.site.cellId)}
          >
            {placed.facilityType === 'VEGETATIVE_SWALE'
              ? '이 수로의 선행 상태 확인'
              : placed.facilityType === 'RAINWATER_CISTERN'
                ? '이 이용조의 시작 저류 비교'
                : '이 시설의 시작 수분 비교'}
          </button>
          <p>
            {placed.facilityType === 'VEGETATIVE_SWALE'
              ? '식생수로의 선행 관측 이후 상태를 확인합니다. 초기 포화도는 적용되지 않아 건습 비교를 제공하지 않습니다.'
              : placed.facilityType === 'RAINWATER_CISTERN'
                ? '자연배수·수요 인출 각각에서 빈 이용조와 가득 찬 이용조의 선행 7일 이후 상태를 비교합니다.'
                : '선택 시설 한 곳의 건조·포화 시작 조건을 추가 계산합니다. 일반 계산보다 시간이 더 걸립니다.'}
          </p>
          {placed.facilityType === 'PERMEABLE_PAVEMENT' && (
            <>
              <button
                className="outline-button"
                disabled={!s.design.ready || working || !s.selectedRain}
                onClick={() =>
                  void s.calculate(undefined, placed.site.districtId, placed.site.cellId)
                }
              >
                이 위치의 투수포장 막힘 조건 비교
              </button>
              <p>
                공개 실험의 새 블록·협잡물 두 조건을 비교합니다. 설치 설계와 순위는 그대로
                유지됩니다.
              </p>
            </>
          )}
        </div>
      )}
      {placed && !result && !finalLocked && (
        <p role="status">
          {selected?.before
            ? '설치 전입니다.'
            : selected?.requestError ||
                selected?.state === 'FAILED' ||
                selected?.state === 'REJECTED'
              ? '이 시설의 누적 효과를 계산하지 못했습니다.'
              : '이 시설의 누적 효과 계산을 기다리는 중입니다.'}
        </p>
      )}
      {placed && result && calculation && !finalLocked && (
        <section className="historical-result" aria-label="과거 강우 비교 결과">
          <h3>이 시설의 재생 시각까지 누적 효과</h3>
          {authenticated && (
            <a className="text-button" href={`/api/v1/historical/${selected.jobId}/bundle`}>
              재현 자료 다운로드
            </a>
          )}
          <strong data-effect={(score?.differenceM3 ?? 0) < 0 ? 'increase' : 'decrease'}>
            {score
              ? `${physicalAmount(score.differenceM3)} m³`
              : selected.before
                ? '설치 전'
                : '누적 기록 없음'}
          </strong>
          <p>시설 없는 조건 대비 평가체적 감소</p>
          {score && <p>{time(score.at)}까지 · 분 종료 기록 · 미래 결과 제외</p>}
          {(score?.differenceM3 ?? 0) < 0 && <p>음수는 평가체적 증가를 뜻합니다.</p>}
          <dl>
            <dt>시설 없음</dt>
            <dd>{score ? physicalAmount(score.baselineAccountedM3) : '—'}m³</dd>
            <dt>이 시설 설치</dt>
            <dd>{score ? physicalAmount(score.designAccountedM3) : '—'}m³</dd>
          </dl>
          <p>
            선택한 표면의 유출·배수·순저류 합 비교입니다. 구 전체 유출량이나 실제 침수 예측이
            아닙니다.
          </p>
          <p>작은 차이는 물수지 오차보다 작을 수 있습니다. 현장 효과로 확정하지 않습니다.</p>
          {calculation.initializationSensitivity?.cellId === placed.site.cellId && (
            <details>
              <summary>사건 전체 창의 시작 수분·저류 비교 · 누적 효과와 별도</summary>
              <InitializationSensitivityEvidence value={calculation.initializationSensitivity} />
            </details>
          )}
          {calculation.pavementMaintenanceComparison?.cellId === placed.site.cellId && (
            <details>
              <summary>사건 전체 창의 투수포장 막힘 비교 · 누적 효과와 별도</summary>
              <PavementMaintenanceEvidence value={calculation.pavementMaintenanceComparison} />
            </details>
          )}
          {result.runoffComparison && (
            <details>
              <summary>{result.cellId} · 설치부터 종료까지 전체 계산 상세</summary>
              <RunoffComparison value={result.runoffComparison} contract={result.designContract} />
              {result.cistern && <CisternGameEvidence value={result.cistern} />}
            </details>
          )}
          <details>
            <summary>계산 조건</summary>
            {(result.initialization || result.facilityDesign || result.costRecord) && (
              <details>
                <summary>{result.cellId} · 시작 수분·시설 제원</summary>
                {result.initialization && <InitializationEvidence value={result.initialization} />}
                {result.facilityDesign && <FacilityProfileEvidence {...result.facilityDesign} />}
                {result.costRecord && (
                  <CostRecordEvidence
                    value={result.costRecord}
                    lifeCycleCost={result.lifeCycleCost}
                  />
                )}
              </details>
            )}
            {calculation.assumptions.map((v) => (
              <p key={v}>{v}</p>
            ))}
            <p>EPA SWMM {calculation.engineVersion} · 현장 보정 전</p>
          </details>
        </section>
      )}
    </FacilityPlacementPanel>
  );
}
import { CisternGameEvidence } from '../../facility/view/CisternGameEvidence';
