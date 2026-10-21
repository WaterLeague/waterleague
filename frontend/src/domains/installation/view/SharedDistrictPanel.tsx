import { SiteScores } from '../../weekly/view/SiteScores';
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
export function SharedDistrictPanel({
  onClose,
  competition,
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
  onLogin,
  onAccount,
  onLocate,
  feedback,
}: {
  competition?: { permits: boolean };
  account: Account | null;
  districtId: string;
  districtName: string;
  onClose?: () => void;
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
  onLogin: () => void;
  onAccount: (a: Account) => void;
  onLocate: () => void;
}) {
  const [choice, setChoice] = useState(''),
    [affiliation, setAffiliation] = useState<AffiliationType>('RESIDENT'),
    [saving, setSaving] = useState(false),
    [membershipError, setMembershipError] = useState('');
  const own =
    !!account &&
    account.role === 'MEMBER' &&
    (competition ? competition.permits : account.districtId === districtId);
  return (
    <FacilityPlacementPanel
      onClose={onClose}
      site={site}
      type={type}
      area={area}
      onType={onType}
      onArea={onArea}
      districtName={districtName}
      context={competition ? '대회 설치 구' : own ? '내 소속 구' : '상태 조회'}
      feedback={feedback}
      budget={budget}
      remaining={remaining}
      limit={budget?.policy.personalLimitKrw ?? 0}
      budgetReady={budgetReady}
      busy={busy}
      canInstall={own}
      readOnlyMessage={
        competition
          ? '대회 참가 여부와 개최 기간·허용 구를 확인해 주세요.'
          : account
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
              {competition ? '로그인하고 대회에 참가' : '로그인하고 우리 구에 설치'}
            </button>
          ) : !competition && account.role === 'MEMBER' && !account.districtId ? (
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
          ) : !competition && !own && account.districtId ? (
            <button className="outline-button shared-join" onClick={onLocate}>
              내 소속 구로 이동 <MapPin size={14} />
            </button>
          ) : null}
        </>
      }
    >
      {site && !competition && (
        <SiteScores
          key={site.districtId + ':' + site.cellId}
          districtId={site.districtId}
          cellId={site.cellId}
          viewerId={account?.id ?? null}
        />
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
