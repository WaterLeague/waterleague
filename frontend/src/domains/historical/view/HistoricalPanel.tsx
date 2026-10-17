import { Leaf, Play, Pause, Trash2 } from 'lucide-react';
import type { HistoricalState } from '../controller/useHistorical';
import type { SharedSite } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities, won, format } from '../../game/service/gameService';
import './historical.css';
const time = (s: string) =>
  new Date(s).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Seoul',
  });
export function HistoricalTimeline({ state: s }: { state: HistoricalState }) {
  return (
    <section className="historical-weather" aria-label="재해 강우 재생">
      <label>
        재해 기록
        <select
          aria-label="재해 사건 선택"
          value={s.eventId}
          disabled={!s.events.length}
          onChange={(e) => s.setEventId(e.target.value)}
        >
          {!s.events.length && <option value="">재해 기록 불러오는 중</option>}
          {s.events.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
        </select>
      </label>
      {s.event && (
        <div className="historical-event-note">
          <p>{s.event.summary}</p>
          <a href={s.event.evidenceUrl} target="_blank" rel="noreferrer">
            {s.event.evidenceTitle} ↗
          </a>
        </div>
      )}
      {s.event && !s.selectedRain && (
        <p role="status">
          선택한 구의 이 사건 관측자료를 확보하지 못했습니다. 다른 지역의 값을 대신 표시하지
          않습니다.
        </p>
      )}
      {s.frameCount > 0 && (
        <>
          <div className="historical-clock">
            <button
              aria-label={s.playing ? '강우 일시정지' : '강우 재생'}
              onClick={() => s.setPlaying((v) => !v)}
            >
              {s.playing ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <time>{s.at && time(s.at)} KST</time>
            <strong>
              {s.selectedRain ? `1분 ${format.format(s.rainMm)} mm` : '선택 구 관측 없음'}
            </strong>
            <label>
              속도
              <select
                aria-label="강우 재생 속도"
                value={s.speed}
                onChange={(e) => s.setSpeed(Number(e.target.value))}
              >
                {[1, 4, 15, 60].map((v) => (
                  <option key={v} value={v}>
                    {v}분/초
                  </option>
                ))}
              </select>
            </label>
          </div>
          <input
            type="range"
            aria-label="재해 강우 재생 시각"
            min="0"
            max={s.frameCount - 1}
            value={s.index}
            onChange={(e) => {
              s.setIndex(Number(e.target.value));
              s.setPlaying(false);
            }}
          />
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
                const r = (s.selectedRain ?? s.event!.regions[0]).depthsMm;
                s.setIndex(r.indexOf(Math.max(...r)));
                s.setPlaying(false);
              }}
            >
              강우 최대
            </button>
          </div>
          <small>
            {s.selectedRain &&
              `${s.selectedRain.stationName} AWS · 대표 지점에서 ${s.selectedRain.distanceKm}km · 관측 창 누적 ${s.selectedRain.totalDepthMm}mm`}
            <br />
            현재 공개 지형에 당시 강우 적용 · 당시 침수 피해 복원 아님 · 구별 관측 강우에 따라
            빗줄기 표시
          </small>
        </>
      )}
    </section>
  );
}
export function HistoricalPanel({
  state: s,
  site,
  type,
  area,
  onType,
  onArea,
  onLogin,
  authenticated,
  error,
}: {
  state: HistoricalState;
  site: SharedSite | null;
  type: FacilityType | '';
  area: string;
  onType: (t: FacilityType) => void;
  onArea: (a: string) => void;
  onLogin: () => void;
  authenticated: boolean;
  error: string;
}) {
  const placed = s.drafts.find(
    (d) => d.site.districtId === site?.districtId && d.site.cellId === site?.cellId
  );
  const cost = site && type ? Number(area) * site.unitCosts[type] : 0;
  const valid =
    site &&
    type &&
    site.allowedTypes.includes(type) &&
    Number(area) > 0 &&
    Number(area) <= site.maxAreaM2 &&
    cost <= s.remaining;
  const working = s.busy || s.job?.state === 'QUEUED' || s.job?.state === 'RUNNING';
  return (
    <aside className="inspector shared-inspector historical-inspector" aria-label="재해 모드 설계">
      <span className="shared-site-kind">실제 재해 강우로 설계 비교</span>
      <h2 className="shared-site-title">{site?.name ?? '서울의 빈 공간을 연구하세요'}</h2>
      <p className="micro-note">
        공동 모드와 같은 공개 후보입니다. 연구 배치는 현재 공동 시설에 반영되지 않습니다.
      </p>
      {!site ? (
        <div className="shared-selection-empty">
          <Leaf size={28} />
          <p>구를 고르고 지도나 위치 목록에서 후보를 선택하세요.</p>
        </div>
      ) : placed ? (
        <div className="shared-occupied">
          <strong>
            {facilities[placed.facilityType].name} · {placed.areaM2}m²
          </strong>
          <button className="outline-button" onClick={() => s.remove(placed.marker.id)}>
            <Trash2 size={14} /> 설계에서 제거
          </button>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (valid && type) s.add(site, type, Number(area));
          }}
        >
          <div className="facility-options">
            {site.allowedTypes.map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={type === t}
                className={type === t ? 'selected' : ''}
                onClick={() => onType(t)}
              >
                {facilities[t].name}
              </button>
            ))}
          </div>
          <label className="area-input">
            설치 면적{' '}
            <span>
              <input
                aria-label="연구 설치 면적"
                type="number"
                min="0.01"
                max={site.maxAreaM2}
                step="0.01"
                required
                value={area}
                onChange={(e) => onArea(e.target.value)}
              />{' '}
              m²
            </span>
          </label>
          <small>최대 {site.maxAreaM2.toLocaleString('ko-KR')}m² · 공개 도형 면적</small>
          <div className="placement-cost">
            <span>설치 비용</span>
            <strong>{won(cost)}</strong>
          </div>
          <button className="solid-button" disabled={!valid}>
            연구 설계에 추가
          </button>
        </form>
      )}
      <div className="historical-design-summary">
        <strong>이 구의 연구 설계 · {s.current.length}곳</strong>
        <small>남은 예산 {won(s.remaining)}</small>
        {s.current.map((d) => (
          <div key={d.marker.id}>
            <span>
              {d.site.name} · {d.areaM2}m²
            </span>
            <button
              aria-label={d.site.name + ' 연구 배치 제거'}
              onClick={() => s.remove(d.marker.id)}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      {authenticated ? (
        <button
          className="solid-button"
          disabled={working || !s.current.length || !s.lab}
          onClick={() => void s.calculate()}
        >
          {working ? '관측 강우로 계산 중' : '이 강우로 비교 계산'}
        </button>
      ) : (
        <button className="solid-button" onClick={onLogin}>
          로그인 후 계산
        </button>
      )}
      {(error || s.error || s.job?.message) && (
        <p role="alert" className="shared-error">
          {error || s.error || s.job?.message}
        </p>
      )}
      {s.currentResult && (
        <section className="historical-result" aria-label="과거 강우 비교 결과">
          <h3>계산 결과</h3>
          <a className="text-button" href={`/api/v1/historical/${s.job!.id}/bundle`}>
            재현 자료 다운로드
          </a>
          <strong>{format.format(s.currentResult.differenceM3)} m³</strong>
          <p>시설 없는 조건 대비 평가체적 감소</p>
          <dl>
            <dt>시설 없음</dt>
            <dd>{format.format(s.currentResult.baselineAccountedM3)}m³</dd>
            <dt>현재 연구 설계</dt>
            <dd>{format.format(s.currentResult.designAccountedM3)}m³</dd>
          </dl>
          <p>
            선택한 표면의 유출·배수·순저류 합 비교입니다. 구 전체 유출량이나 실제 침수 예측이
            아닙니다.
          </p>
          <details>
            <summary>계산 조건</summary>
            {s.currentResult.assumptions.map((v) => (
              <p key={v}>{v}</p>
            ))}
            <p>EPA SWMM {s.currentResult.engineVersion} · 현장 보정 전</p>
          </details>
        </section>
      )}
    </aside>
  );
}
