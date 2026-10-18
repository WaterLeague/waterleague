import { FacilityProfileEvidence } from './FacilityProfileEvidence';
import type { FacilityType } from '../../game/entity/game';
import type { SharedSite } from '../../installation/entity/installation';
import { useFacilityCatalog } from '../controller/useFacilityCatalog';
export function FacilityDesignEvidence({ site, type }: { site: SharedSite; type: FacilityType }) {
  const enabled = !!site.facilityDesignSet?.id.match(/^EPA_LID_PUBLIC_DESIGNS_V[12]$/);
  const { catalog, failed } = useFacilityCatalog(enabled, site.facilityDesignSet?.id);
  if (!enabled) return null;
  if (failed)
    return <p className="micro-note">시설 제원을 불러오지 못했습니다. 화면을 새로고침해 주세요.</p>;
  if (!catalog) return <p className="micro-note">공개 시설 제원을 불러오는 중입니다.</p>;
  const profile = catalog.profiles[type];
  if (!profile) return null;
  return (
    <FacilityProfileEvidence
      profile={profile}
      source={catalog.source}
      limitations={catalog.limitations}
      nativeSoilBoundary={
        type === 'RAIN_GARDEN'
          ? site.physicalInputs?.rainGardenBoundary
          : type === 'BIORETENTION'
            ? site.physicalInputs?.bioretentionBoundary
            : undefined
      }
    >
      {site.initializationPolicy && (
        <p>
          시작 수분은 선행 7일의 실제 강우·기상을 재생해 계산합니다. 사전 계산의 효과는 점수에서
          제외하며, 시작 상태는 토양수분 실측값이 아닙니다.
        </p>
      )}
      <p>
        시공비는 별도의 공개 참고 단가입니다. 구조하중·배수구·재료 성적서 검토를 대신하지 않습니다.
      </p>
    </FacilityProfileEvidence>
  );
}
