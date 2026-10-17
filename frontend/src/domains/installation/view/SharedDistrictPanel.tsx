import { useState } from 'react';
import { Leaf, Grid2X2, House, MapPin, Check, Trash2 } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { SharedSite, SharedInstallation } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { facilities } from '../../game/service/gameService';
import { DistrictFields } from '../../district/view/DistrictFields';
import type { AffiliationType } from '../../district/entity/district';
import { selectAccountDistrict } from '../../account/repository/accountRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
import { BudgetEvidence } from '../../budget/view/BudgetEvidence';
import type { Budget } from '../../budget/dto/budgetDto';
import { CostEstimate } from './CostEstimate';
import { PhysicsPanel } from '../../physics/view/PhysicsPanel';
const icons = { RAIN_GARDEN: Leaf, PERMEABLE_PAVEMENT: Grid2X2, GREEN_ROOF: House };
const won = (n: number) =>
  new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(n) + '원';
export function SharedDistrictPanel({
  account,
  districtId,
  districtName,
  site,
  occupied,
  type,
  area,
  onType,
  onArea,
  remaining,
  budget,
  budgetReady,
  busy,
  error,
  onInstall,
  onRemove,
  onLogin,
  onAccount,
  onLocate,
  feedback,
}: {
  account: Account | null;
  districtId: string;
  districtName: string;
  site: SharedSite | null;
  occupied?: SharedInstallation;
  type: FacilityType | '';
  area: string;
  onType: (t: FacilityType) => void;
  onArea: (a: string) => void;
  remaining: number;
  budget: Budget | null;
  budgetReady: boolean;
  busy: boolean;
  error: string;
  feedback: string;
  onInstall: (s: SharedSite, t: FacilityType, a: number) => Promise<boolean>;
  onRemove: (id: string) => Promise<boolean>;
  onLogin: () => void;
  onAccount: (a: Account) => void;
  onLocate: () => void;
}) {
  const [choice, setChoice] = useState(''),
    [affiliation, setAffiliation] = useState<AffiliationType>('RESIDENT'),
    [saving, setSaving] = useState(false),
    [membershipError, setMembershipError] = useState('');
  const own = !!account && account.role === 'MEMBER' && account.districtId === districtId;
  const cost = site && type ? (Number(area) || 0) * site.unitCosts[type] : 0;
  const valid =
    budgetReady &&
    !!site &&
    !!type &&
    site.allowedTypes.includes(type) &&
    Number(area) > 0 &&
    Number(area) <= site.maxAreaM2 &&
    cost <= remaining;
  return (
    <aside className="inspector shared-inspector" aria-label="공동 시설 설치">
      <div className="round-feedback" role="status">
        <MapPin size={17} />
        <div>
          <strong>{feedback || (site ? '선택한 위치' : '우리 구의 빈 곳을 찾아보세요')}</strong>
          <span>
            {districtName
              ? districtName + (own ? ' · 내 소속 구' : ' · 상태 조회')
              : '서울 25개 구 공동 지도'}
          </span>
        </div>
      </div>
      {!account ? (
        <button className="solid-button shared-join" onClick={onLogin}>
          로그인하고 우리 구에 설치
        </button>
      ) : account.role === 'MEMBER' && !account.districtId ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setSaving(true);
            setMembershipError('');
            try {
              onAccount(await selectAccountDistrict(choice, affiliation));
            } catch (e) {
              setMembershipError(errorMessage(e));
            } finally {
              setSaving(false);
            }
          }}
        >
          <DistrictFields
            districtId={choice}
            affiliationType={affiliation}
            onDistrict={setChoice}
            onType={setAffiliation}
          />
          <button className="solid-button" disabled={saving}>
            소속 구 확정
          </button>
          {membershipError && <p role="alert">{membershipError}</p>}
        </form>
      ) : !own && account.districtId ? (
        <button className="outline-button shared-join" onClick={onLocate}>
          내 소속 구로 이동 <MapPin size={14} />
        </button>
      ) : null}
      {!site ? (
        <div className="shared-selection-empty">
          <Leaf size={30} />
          <h2>작은 시설, 함께 만드는 변화</h2>
          <p>시설을 고른 뒤 지도에 표시된 후보나 위치 목록에서 빈 곳을 선택하세요.</p>
          <p>설치는 내 소속 구에서만 가능합니다. 다른 구의 시설도 둘러볼 수 있습니다.</p>
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
              <h3>{facilities[occupied.facilityType].name} 설치 완료</h3>
              <p>
                {occupied.ownerName} · {occupied.areaM2.toLocaleString('ko-KR')} m²
              </p>
              <strong>{won(occupied.cost)}</strong>
              {occupied.ownerId === account?.id ? (
                <button
                  className="outline-button"
                  disabled={busy}
                  onClick={() => void onRemove(occupied.id)}
                >
                  <Trash2 size={14} /> 내 시설 철거
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
                if (own && valid && type) void onInstall(site, type, Number(area));
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
                      onClick={() => onType(t)}
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
                    onChange={(e) => onArea(e.target.value)}
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
                value={Math.min(site.maxAreaM2, Number(area) || 0.01)}
                onChange={(e) => onArea(e.target.value)}
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
              {type && (
                <CostEstimate
                  site={site}
                  type={type}
                  area={Number(area)}
                  remaining={remaining}
                  onArea={onArea}
                />
              )}
              {cost > remaining && own && (
                <p role="alert" className="shared-error">
                  남은 예산을 초과했습니다.
                </p>
              )}
              {own ? (
                <button className="solid-button shared-install" disabled={busy || !valid}>
                  {busy ? '설치 확인 중' : '이 위치에 설치'}
                </button>
              ) : (
                <p className="shared-readonly">
                  {account
                    ? '내 소속 구에서만 설치할 수 있습니다.'
                    : '로그인 후 내 소속 구에 설치할 수 있습니다.'}
                </p>
              )}
              <p className="shared-preview-note">
                점선 시설은 미리보기입니다. 설치 버튼을 누르면 모두의 지도에 반영됩니다.
              </p>
            </form>
          )}
        </>
      )}
      {error && (
        <p className="shared-error" role="alert">
          {error}
        </p>
      )}
      {occupied && <PhysicsPanel key={occupied.id} installationId={occupied.id} />}
      {budget && (
        <div className="budget-box">
          <span>서울 공동 배치예산 잔액</span>
          <strong>{won(remaining)}</strong>
          <div className="shared-budget-track">
            <span
              style={{
                width: Math.max(0, Math.min(100, (remaining / budget.policy.limitKrw) * 100)) + '%',
              }}
            />
          </div>
        </div>
      )}
      <BudgetEvidence value={budget} />
      <p className="shared-evidence-note">
        공개 도형 기반 실험 후보 · 현장 시공 적합성 미확인
        <br />
        예산은 게임 설계 조건 · 면적 한계는 공개 도형 기준
      </p>
    </aside>
  );
}
