import type { ReactNode } from 'react';
import { Leaf, Grid2X2, House, MapPin, Check, Trash2 } from 'lucide-react';
import type { SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities, won } from '../../game/service/gameService';
import { BudgetEvidence } from '../../budget/view/BudgetEvidence';
import type { Budget } from '../../budget/dto/budgetDto';
import { CostEstimate } from './CostEstimate';
import { FacilityDesignEvidence } from '../../facility/view/FacilityDesignEvidence';
import { PhysicalInputEvidence } from './PhysicalInputEvidence';
const icons = { RAIN_GARDEN: Leaf, PERMEABLE_PAVEMENT: Grid2X2, GREEN_ROOF: House };
type Placed = {
  facilityType: FacilityType;
  areaM2: number;
  cost: number;
  ownerName: string;
  onRemove?: () => void;
};
export type FacilityPlacementProps = {
  site: SharedSite | null;
  type: FacilityType | '';
  area: string;
  onType: (type: FacilityType) => void;
  onArea: (area: string) => void;
  districtName: string;
  context: string;
  feedback?: string;
  budget: Budget | null;
  remaining: number;
  limit: number;
  budgetReady: boolean;
  busy: boolean;
  canInstall: boolean;
  readOnlyMessage?: string;
  onInstall: () => void;
  occupied?: Placed;
  research?: boolean;
  error?: string;
  access?: ReactNode;
  children?: ReactNode;
};
export function FacilityPlacementPanel(p: FacilityPlacementProps) {
  const { site, type, area, remaining, occupied } = p;
  const numericArea = Number(area);
  const cost = site && type ? numericArea * site.unitCosts[type] : 0;
  const valid =
    p.budgetReady &&
    !!site &&
    !!type &&
    site.allowedTypes.includes(type) &&
    Number.isFinite(numericArea) &&
    numericArea > 0 &&
    numericArea <= site.maxAreaM2 &&
    cost <= remaining;
  return (
    <aside className="inspector shared-inspector" aria-label="시설 설치">
      <div className="round-feedback" role="status">
        <MapPin size={17} />
        <div>
          <strong>
            {p.feedback || (site ? '선택한 위치' : '시설을 설치할 빈 곳을 찾아보세요')}
          </strong>
          <span>
            {p.districtName || '서울 25개 구'} · {p.context}
          </span>
        </div>
      </div>
      {p.access}
      {!site ? (
        <div className="shared-selection-empty">
          <Leaf size={30} />
          <h2>작은 시설, 함께 만드는 변화</h2>
          <p>시설을 고른 뒤 지도에 표시된 후보나 위치 목록에서 빈 곳을 선택하세요.</p>
          <p>
            {p.research
              ? '연구 배치는 이 재해의 비교 계산에 사용됩니다.'
              : '설치는 내 소속 구에서만 가능합니다. 다른 구의 시설도 둘러볼 수 있습니다.'}
          </p>
        </div>
      ) : (
        <>
          <span className="shared-site-kind">
            {site.kind === 'ROOF' ? '옥상 후보' : '지상 주차장 후보'}
          </span>
          <h2 className="shared-site-title">{site.name}</h2>
          {occupied ? (
            <div className="shared-occupied">
              <Check size={22} />
              <h3>
                {facilities[occupied.facilityType].name} {p.research ? '배치 완료' : '설치 완료'}
              </h3>
              <p>
                {occupied.ownerName} · {occupied.areaM2.toLocaleString('ko-KR')} m²
              </p>
              <strong>{won(occupied.cost)}</strong>
              {occupied.onRemove ? (
                <button className="outline-button" disabled={p.busy} onClick={occupied.onRemove}>
                  <Trash2 size={14} />
                  {p.research ? '설계에서 제거' : '내 시설 철거'}
                </button>
              ) : (
                <p>
                  다른 회원이 설치한 위치입니다.
                  <br />빈 위치를 선택해 주세요.
                </p>
              )}
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (p.canInstall && valid) p.onInstall();
              }}
            >
              <div className="facility-options" aria-label="설치 시설 종류">
                {site.allowedTypes.map((t) => {
                  const Icon = icons[t];
                  return (
                    <button
                      type="button"
                      key={t}
                      className={type === t ? 'selected' : ''}
                      aria-pressed={type === t}
                      onClick={() => p.onType(t)}
                    >
                      <Icon size={18} />
                      <span>{facilities[t].name}</span>
                    </button>
                  );
                })}
              </div>
              {type && (
                <p className="shared-facility-description">{facilities[type].description}</p>
              )}
              <label className="area-input">
                설치 면적{' '}
                <span>
                  <input
                    type="number"
                    min="0.01"
                    max={site.maxAreaM2}
                    step="0.01"
                    required
                    value={area}
                    onChange={(e) => p.onArea(e.target.value)}
                  />{' '}
                  m²
                </span>
              </label>
              <input
                className="area-slider"
                aria-label="설치 면적 조절"
                type="range"
                min="0.01"
                max={site.maxAreaM2}
                step="0.01"
                value={Math.min(site.maxAreaM2, numericArea || 0.01)}
                onChange={(e) => p.onArea(e.target.value)}
              />
              <div className="shared-area-limit">
                최대 {site.maxAreaM2.toLocaleString('ko-KR')} m² · 공개 도형 면적
              </div>
              <p className="micro-note">
                도형 밖 면적 배치만 제한합니다. 실제 시공 가능 면적과 구조안전은 확인되지
                않았습니다.
                {site.inflowPolicy === 'DIRECT_RAINFALL_ONLY' &&
                  ' 시설 자체에 내리는 비만 계산하며, 주변 유출의 시설 유입은 가산하지 않습니다.'}
              </p>
              {type && <FacilityDesignEvidence site={site} type={type} />}
              {type && (
                <CostEstimate
                  site={site}
                  type={type}
                  area={numericArea}
                  remaining={remaining}
                  onArea={p.onArea}
                />
              )}
              {cost > remaining && p.canInstall && (
                <p role="alert" className="shared-error">
                  남은 예산을 초과했습니다.
                </p>
              )}
              {p.canInstall ? (
                <button className="solid-button shared-install" disabled={p.busy || !valid}>
                  {p.busy ? '설치 확인 중' : p.research ? '연구 설계에 추가' : '이 위치에 설치'}
                </button>
              ) : (
                <p className="shared-readonly">{p.readOnlyMessage}</p>
              )}
              <p className="shared-preview-note">
                점선 시설은 미리보기입니다.{' '}
                {p.research
                  ? '추가한 배치는 현재 공동 시설과 분리해 계산합니다.'
                  : '설치 버튼을 누르면 모두의 지도에 반영됩니다.'}
              </p>
            </form>
          )}
        </>
      )}
      {p.error && (
        <p className="shared-error" role="alert">
          {p.error}
        </p>
      )}
      {p.budget && (
        <div className="budget-box">
          <span>{p.research ? '내 재해 설계' : '내 설치 예산'} 잔액</span>
          <strong>{won(remaining)}</strong>
          <div className="shared-budget-track">
            <span
              style={{
                width: `${p.limit > 0 ? Math.max(0, Math.min(100, (remaining / p.limit) * 100)) : 0}%`,
              }}
            />
          </div>
        </div>
      )}
      <BudgetEvidence value={p.budget} research={p.research} />
      {site && !occupied && <PhysicalInputEvidence site={site} />}
      {p.children}
      <p className="shared-evidence-note">
        공개 도형 기반 실험 후보 · 현장 시공 적합성 미확인
        <br />
        예산은 게임 설계 조건 · 면적 한계는 공개 도형 기준
      </p>
    </aside>
  );
}
