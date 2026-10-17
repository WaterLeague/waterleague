import { useState } from 'react';
import type { Account } from '../../account/entity/account';
import type { SharedSite, SharedInstallation } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { DistrictFields } from '../../district/view/DistrictFields';
import type { AffiliationType } from '../../district/entity/district';
import { selectAccountDistrict } from '../../account/repository/accountRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
import './installation.css';
const names: Record<FacilityType, string> = {
  RAIN_GARDEN: '빗물정원',
  PERMEABLE_PAVEMENT: '투수포장',
  GREEN_ROOF: '녹화지붕',
};
const won = (n: number) => new Intl.NumberFormat('ko-KR').format(n) + '원';
export function SharedDistrictPanel({
  account,
  districtId,
  districtName,
  sites,
  installations,
  selected,
  onSelect,
  busy,
  error,
  onInstall,
  onRemove,
  onLogin,
  onAccount,
}: {
  account: Account | null;
  districtId: string;
  districtName: string;
  sites: SharedSite[];
  installations: SharedInstallation[];
  selected: string;
  onSelect: (id: string) => void;
  busy: boolean;
  error: string;
  onInstall: (s: SharedSite, t: FacilityType, a: number) => Promise<boolean>;
  onRemove: (id: string) => Promise<boolean>;
  onLogin: () => void;
  onAccount: (a: Account) => void;
}) {
  const [choice, setChoice] = useState(''),
    [affiliation, setAffiliation] = useState<AffiliationType>('RESIDENT'),
    [saving, setSaving] = useState(false),
    [membershipError, setMembershipError] = useState('');
  const site = sites.find((s) => s.cellId === selected),
    occupied = installations.find((i) => i.cellId === selected);
  const own = !!account && account.role === 'MEMBER' && account.districtId === districtId;
  return (
    <section className="shared-district-panel">
      <span className="city-mission-kicker">서울 공동 설치</span>
      <h2>{districtName || '함께 만드는 서울'}</h2>
      {!account ? (
        <button className="solid-button" onClick={onLogin}>
          소속 구로 참여하기
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
      ) : (
        <p>
          {own
            ? '우리 구의 빈 위치에 시설을 설치하세요.'
            : '현재 구는 읽기 전용입니다. 다른 구의 설치 상태도 확인할 수 있습니다.'}
        </p>
      )}
      {own && sites.length > 0 && (
        <p className="shared-budget">
          남은 예산{' '}
          <strong>
            {won(
              sites[0].budget -
                installations
                  .filter((i) => i.ownerId === account?.id)
                  .reduce((sum, i) => sum + i.cost, 0)
            )}
          </strong>
        </p>
      )}
      {!districtId ? (
        <p>지도에서 구를 선택해 현재 시설을 확인하세요.</p>
      ) : (
        <>
          <p className="shared-site-count">
            {installations.length}곳 설치 · {Math.max(0, sites.length - installations.length)}곳
            비어 있음
          </p>
          <div className="shared-site-list" role="group" aria-label="공유 설치 위치">
            {sites.map((s) => {
              const i = installations.find((v) => v.cellId === s.cellId);
              return (
                <button
                  key={s.cellId}
                  aria-pressed={s.cellId === selected}
                  onClick={() => onSelect(s.cellId)}
                >
                  <strong>{s.cellId}</strong>
                  <span>{i ? names[i.facilityType] : '빈 위치'}</span>
                  <small>{i ? i.ownerName : s.kind === 'ROOF' ? '옥상' : '지상'}</small>
                </button>
              );
            })}
          </div>
          {site && (
            <div className="shared-site-editor">
              <h3>
                {site.cellId} · {site.name}
              </h3>
              {occupied ? (
                <>
                  <p>
                    <b>{occupied.ownerName}</b>님의 {names[occupied.facilityType]} ·{' '}
                    {occupied.areaM2} m²
                  </p>
                  <p>{won(occupied.cost)} · 설치 완료</p>
                  {occupied.ownerId === account?.id && (
                    <button
                      className="outline-button"
                      disabled={busy}
                      onClick={() => void onRemove(occupied.id)}
                    >
                      내 시설 철거
                    </button>
                  )}
                  {occupied.ownerId !== account?.id && (
                    <p>이미 설치된 위치입니다. 중복 설치할 수 없습니다.</p>
                  )}
                </>
              ) : own ? (
                <InstallEditor key={site.cellId} site={site} busy={busy} onInstall={onInstall} />
              ) : (
                <p>소속 구 회원만 설치할 수 있습니다.</p>
              )}
            </div>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="shared-error">
          {error}
        </p>
      )}
      <small>
        공개 도형 기반 후보 위치 · 현장 시공 적합성 미확인
        <br />
        예산·시설은 게임 설계 조건이며 실제 사업비 아님
      </small>
    </section>
  );
}
function InstallEditor({
  site,
  busy,
  onInstall,
}: {
  site: SharedSite;
  busy: boolean;
  onInstall: (s: SharedSite, t: FacilityType, a: number) => Promise<boolean>;
}) {
  const [type, setType] = useState(site.allowedTypes[0]),
    [area, setArea] = useState(String(Math.min(20, site.maxAreaM2)));
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void onInstall(site, type, Number(area));
      }}
    >
      <label>
        시설
        <select value={type} onChange={(e) => setType(e.target.value as FacilityType)}>
          {site.allowedTypes.map((t) => (
            <option key={t} value={t}>
              {names[t]}
            </option>
          ))}
        </select>
      </label>
      <label>
        설치 면적 · m²
        <input
          type="number"
          min="0.01"
          max={site.maxAreaM2}
          step="0.01"
          required
          value={area}
          onChange={(e) => setArea(e.target.value)}
        />
      </label>
      <p>
        최대 {site.maxAreaM2} m² · {won((Number(area) || 0) * site.unitCosts[type])}
      </p>
      <button
        className="solid-button"
        disabled={busy || !area || Number(area) <= 0 || Number(area) > site.maxAreaM2}
      >
        {busy ? '설치 확인 중' : '이 위치에 설치'}
      </button>
    </form>
  );
}
