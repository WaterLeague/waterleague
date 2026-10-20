import { Fragment, type ReactNode } from 'react';
import type { FacilityEvidence } from '../dto/facilityDto';
import { PavementCleaningEvidence } from './PavementCleaningEvidence';
import './facility-evidence.css';

const labels: Record<string, string> = {
  bottomWidthM: '수로 바닥 폭',
  topWidthM: '설계 상부 폭',
  sideSlope: '측면 경사',
  soilDepthMm: '식재토 두께',
  pavementDepthMm: '투수층 두께',
  storageDepthMm: '쇄석층 두께',
  drainageDepthMm: '배수매트 두께',
  surfaceDepthMm: '표면 저류 깊이',
  conductivityMmH: '시설 재료 투수계수',
  porosity: '식재토 공극률',
  fieldCapacity: '포장용수량',
  wiltingPoint: '시들음점 수분율',
  pavementPorosity: '투수층 공극률',
  storagePorosity: '쇄석층 공극률',
  drainagePorosity: '배수매트 공극률',
  vegetationFraction: '식생 체적비율',
  surfaceRoughness: '표면 조도',
  drainageRoughness: '배수매트 조도',
  conductivitySlope: '투수계수 변화계수',
  suctionMm: '흡인수두',
  imperviousFraction: '포장 불투수비율',
  cloggingFactor: '막힘 계수',
};
const bases: Record<string, string> = {
  EXPLICIT_DESIGN_NOT_SITE_MEASURED: '현장 실측과 구분한 설계값',
  DERIVED_CROSS_SECTION: '단면 치수에서 계산',
  LITERATURE_ENGINEERED_SOIL_ESTIMATE: '문헌 식재토의 추정값',
  PUBLIC_RANGE_DESIGN_SELECTION: '문헌 범위에서 선택한 설계값',
  PUBLISHED_TYPICAL_DERIVED_SOIL: '문헌 대표값·추정값',
  UNRESOLVED_DESIGN_ASSUMPTION: '실측 미확보 설계 가정',
  DESIGN_CONTINUOUS_PERMEABLE_PAVEMENT: '연속 투수포장 설계 조건',
  DESIGN_INSTANT_OVERFLOW: '즉시 월류 설계 조건',
  DESIGN_NEW_UNCLOGGED: '신설·미막힘 설계 조건',
};
const soilBases: Record<NonNullable<FacilityEvidence['nativeSoilBoundary']>['basis'], string> = {
  TEXTURE_CLASS_LITERATURE_ESTIMATE: '공개 토성군·문헌 추정',
  PUBLIC_REFERENCE_SCENARIO_NOT_LOCAL_MEASUREMENT: '공통 문헌 토양 조건·현장 실측 아님',
  UNRESOLVED_DESIGN_ASSUMPTION: '토성 미확보·설계 가정',
};
const display = (value: number, unit: string) =>
  unit === 'fraction'
    ? `${(value * 100).toLocaleString('ko-KR', { maximumFractionDigits: 3 })}%`
    : `${value.toLocaleString('ko-KR', { maximumFractionDigits: 6 })}${unit === 'dimensionless' ? '' : ` ${unit}`}`;

export function FacilityProfileEvidence({
  profile,
  source,
  limitations,
  catalogSha256,
  nativeSoilBoundary,
  children,
}: Pick<FacilityEvidence, 'profile' | 'source' | 'limitations' | 'nativeSoilBoundary'> & {
  catalogSha256?: string;
  children?: ReactNode;
}) {
  return (
    <details className="budget-evidence facility-profile-evidence">
      <summary>
        {catalogSha256 ? '계산에 사용한 시설 제원 · ' : ''}
        {profile.summary}
      </summary>
      <p>
        {catalogSha256
          ? '이 계산 결과에 보관된 설계 제원입니다.'
          : '공개 문헌에 따른 설계 제원입니다.'}{' '}
        현장의 기존 시설을 측정한 값은 아닙니다.
      </p>
      <dl className="physical-input-values">
        {Object.entries(profile.parameters).map(([key, p]) => (
          <Fragment key={key}>
            <dt>{labels[key] ?? key}</dt>
            <dd>
              {display(p.value, p.unit)}
              <small>
                {bases[p.basis] ?? p.basis}
                {p.range
                  ? ` · 참고 범위 ${display(p.range[0], p.unit)}–${display(p.range[1], p.unit)}`
                  : ''}{' '}
                · {p.reference}
              </small>
            </dd>
          </Fragment>
        ))}
      </dl>
      {nativeSoilBoundary && (
        <>
          <p>
            원지반 침투율 {display(nativeSoilBoundary.seepageMmH, 'mm/h')} ·{' '}
            {soilBases[nativeSoilBoundary.basis]}
          </p>
          <p>
            차수막 없는 설계 조건입니다. 실제 부지의 차수막·지하수·다짐 상태는 확인되지 않았습니다.
          </p>
        </>
      )}
      {profile.type === 'RG' && !nativeSoilBoundary && (
        <p>
          이전 입력은 원지반 침투 연결이 빠져 침투량을 0으로 계산했습니다. 현장 효과 비교에 사용하지
          마세요.
        </p>
      )}
      {children}
      {profile.type === 'PP' && <PavementCleaningEvidence />}
      {limitations.map((note) => (
        <p key={note}>{note}</p>
      ))}
      <a href={source.url} target="_blank" rel="noreferrer">
        {source.title} · {source.year} · {source.pages.join(', ')}쪽 ↗
      </a>
      {catalogSha256 && <code className="hash-value">계산 제원 SHA-256: {catalogSha256}</code>}
      <code className="hash-value">문헌 SHA-256: {source.sha256}</code>
    </details>
  );
}
