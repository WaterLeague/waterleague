import { SiteScores } from '../../weekly/view/SiteScores';
import { facilities } from '../../game/service/gameService';
import { useState } from 'react';
import { MapPin } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { SharedSite, SharedInstallation } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { DistrictFields } from '../../district/view/DistrictFields';
import type { AffiliationType } from '../../district/entity/district';
import { selectAccountDistrict } from '../../account/repository/accountRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { Budget } from '../../budget/dto/budgetDto';
import { FacilityPlacementPanel } from './FacilityPlacementPanel';
import { PhysicsPanel } from '../../physics/view/PhysicsPanel';
import { InstallationCostRecord } from '../../cost/view/CostRecordEvidence';
import { installationScore } from '../service/installationScore';
export function SharedDistrictPanel({
  onClose,
  account,
  districtId,
  districtName,
  site,
  occupied,
  ownInstallations,
  onSelectInstallation,
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
  onLogin,
  onAccount,
  onLocate,
  feedback,
}: {
  account: Account | null;
  districtId: string;
  districtName: string;
  onClose?: () => void;
  site: SharedSite | null;
  occupied?: SharedInstallation;
  ownInstallations: SharedInstallation[];
  onSelectInstallation: (value: SharedInstallation) => void;
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
  onLogin: () => void;
  onAccount: (a: Account) => void;
  onLocate: () => void;
}) {
  const [choice, setChoice] = useState(''),
    [affiliation, setAffiliation] = useState<AffiliationType>('RESIDENT'),
    [saving, setSaving] = useState(false),
    [membershipError, setMembershipError] = useState('');
  const own = !!account && account.role === 'MEMBER' && account.districtId === districtId;
  return (
    <FacilityPlacementPanel
      onClose={onClose}
      site={site}
      type={type}
      area={area}
      onType={onType}
      onArea={onArea}
      districtName={districtName}
      context={own ? '내 소속 구' : '상태 조회'}
      feedback={feedback}
      budget={budget}
      remaining={remaining}
      limit={budget?.policy.personalLimitKrw ?? 0}
      budgetReady={budgetReady}
      busy={busy}
      canInstall={own}
      readOnlyMessage={
        account
          ? '내 소속 구에서만 설치할 수 있습니다.'
          : '로그인 후 내 소속 구에 설치할 수 있습니다.'
      }
      onInstall={() => {
        if (site && type) void onInstall(site, type, Number(area));
      }}
      occupied={occupied}
      error={error}
      access={
        <>
          {' '}
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
        </>
      }
    >
      {site && (
        <SiteScores
          key={site.districtId + ':' + site.cellId}
          districtId={site.districtId}
          cellId={site.cellId}
          viewerId={account?.id ?? null}
        />
      )}
      {!!ownInstallations.length && (
        <details className="weekly-site-scores" open>
          <summary>내 시설 {ownInstallations.length}곳</summary>
          {ownInstallations.map((value) => (
            <button
              key={value.id}
              className="outline-button"
              onClick={() => onSelectInstallation(value)}
            >
              {facilities[value.facilityType].name} · {value.cellId} ·{' '}
              {value.areaM2.toLocaleString('ko-KR')} m²
              <strong>{installationScore(value)}</strong>
              {value.evaluatedThrough && (
                <small>
                  반영{' '}
                  {new Date(value.evaluatedThrough).toLocaleTimeString('ko-KR', {
                    timeZone: 'Asia/Seoul',
                    hour12: false,
                  })}
                </small>
              )}
            </button>
          ))}
        </details>
      )}
      {occupied && (
        <>
          <InstallationCostRecord key={'cost-' + occupied.id} id={occupied.id} />
          <PhysicsPanel key={occupied.id} installationId={occupied.id} />
        </>
      )}
    </FacilityPlacementPanel>
  );
}
