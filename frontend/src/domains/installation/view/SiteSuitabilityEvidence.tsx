import type { SiteSuitability } from '../dto/siteSuitabilityDto';
import { Fragment } from 'react';

export const eligibilityLabels = {
  ELIGIBLE: '허용 조건 확인',
  CONDITIONAL: '조건 충족 확인 필요',
  PROHIBITED: '금지',
  UNKNOWN: '미확인',
};
const labels = {
  SOIL: '현장 토양',
  SLOPE: '현장 경사',
  GROUNDWATER: '지하수',
  UNDERGROUND_UTILITIES: '지하 지장물',
  TRAFFIC_LOAD: '교통 하중',
  ROOF_STRUCTURAL_LOAD: '옥상 구조 하중',
  WATERPROOFING: '방수',
  DRAINAGE: '배수',
};
export function SiteSuitabilityEvidence({ value }: { value: SiteSuitability }) {
  return (
    <>
      <p>
        현장 적합성 · {eligibilityLabels[value.status]}. 지도 탐색 배치는 실제 시공 승인이 아닙니다.
      </p>
      <dl className="physical-input-values">
        {value.checks.map((row) => (
          <Fragment key={row.id}>
            <dt>{labels[row.id]}</dt>
            <dd>
              {eligibilityLabels[row.status]} · {row.reason}
              {row.evidence && (
                <>
                  {' '}
                  ·{' '}
                  <a href={row.evidence.url} target="_blank" rel="noreferrer">
                    {row.evidence.title} · {row.evidence.reference} ↗
                  </a>
                </>
              )}
            </dd>
          </Fragment>
        ))}
      </dl>
    </>
  );
}
