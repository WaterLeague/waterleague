import { Fragment } from 'react';
import type { FacilityType } from '../../game/entity/game';
import type { SharedSite } from '../../installation/entity/installation';
import { useFacilityCatalog } from '../controller/useFacilityCatalog';
const labels: Record<string, string> = {
  soilDepthMm: '식재토 두께',
  pavementDepthMm: '투수층 두께',
  storageDepthMm: '쇄석층 두께',
  drainageDepthMm: '배수매트 두께',
  surfaceDepthMm: '표면 저류 깊이',
  conductivityMmH: '시설 재료 투수계수',
  porosity: '식재토 공극률',
  fieldCapacity: '포장용수량',
  wiltingPoint: '시들음점 수분율',
};
export function FacilityDesignEvidence({ site, type }: { site: SharedSite; type: FacilityType }) {
  const enabled = site.facilityDesignSet?.id === 'EPA_LID_PUBLIC_DESIGNS_V1';
  const { catalog, failed } = useFacilityCatalog(enabled);
  if (!enabled) return null;
  if (failed)
    return <p className="micro-note">시설 제원을 불러오지 못했습니다. 화면을 새로고침해 주세요.</p>;
  if (!catalog) return <p className="micro-note">공개 시설 제원을 불러오는 중입니다.</p>;
  const profile = catalog.profiles[type];
  return (
    <details className="budget-evidence">
      <summary>{profile.summary}</summary>
      <p>EPA 공개 문헌에 따른 설계 제원입니다. 현장의 기존 시설을 측정한 값은 아닙니다.</p>
      <dl className="physical-input-values">
        {Object.entries(labels)
          .filter(([key]) => profile.parameters[key])
          .map(([key, label]) => {
            const p = profile.parameters[key];
            return (
              <Fragment key={key}>
                <dt>{label}</dt>
                <dd>
                  {p.unit === 'fraction'
                    ? `${(p.value * 100).toFixed(1)}%`
                    : `${p.value.toLocaleString('ko-KR')} ${p.unit}`}
                </dd>
              </Fragment>
            );
          })}
      </dl>
      {site.initializationPolicy && (
        <p>
          시작 수분은 선행 7일의 실제 강우·기상을 재생해 계산합니다. 사전 계산의 효과는 점수에서
          제외하며, 시작 상태는 토양수분 실측값이 아닙니다.
        </p>
      )}
      <p>
        시공비는 별도의 공개 참고 단가입니다. 구조하중·배수구·재료 성적서 검토를 대신하지 않습니다.
      </p>
      <a href={catalog.source.url} target="_blank" rel="noreferrer">
        시설 설계 출처 · EPA 표 6-2~6-6 ↗
      </a>
    </details>
  );
}
