import type { SharedSite } from '../entity/installation';
import { SiteSuitabilityEvidence } from './SiteSuitabilityEvidence';
const number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 });
export function PhysicalInputEvidence({ site }: { site: SharedSite }) {
  const p = site.physicalInputs;
  if (!p) return null;
  return (
    <details className="budget-evidence">
      <summary>이 위치의 계산 입력·현장 적합성</summary>
      {site.suitability && <SiteSuitabilityEvidence value={site.suitability} />}
      <dl className="physical-input-values">
        <dt>도형 기반 유출 폭</dt>
        <dd>{number.format(p.runoffWidthM)} m</dd>
        <dt>도형 장축 길이</dt>
        <dd>{number.format(p.flowLengthM)} m</dd>
        <dt>경사</dt>
        <dd>{number.format(p.slopePercent)}% · 공통 비교 설계값</dd>
        <dt>현장 표면 재료</dt>
        <dd>미확인</dd>
        {p.nImpervious !== undefined && (
          <>
            <dt>불투수 참조 조도</dt>
            <dd>{p.nImpervious} · 공통 문헌값</dd>
          </>
        )}
        {site.kind === 'GROUND' && (
          <>
            <dt>현장 토성</dt>
            <dd>미확인</dd>
            <dt>참조 토양</dt>
            <dd>Loam 문헌 시나리오</dd>
            {p.conductivityMmH !== undefined && (
              <>
                <dt>참조 투수계수</dt>
                <dd>{number.format(p.conductivityMmH)} mm/h</dd>
              </>
            )}
          </>
        )}
      </dl>
      <p>
        유출 폭은 면적/장축의 집약 값입니다. 분리된 면 사이의 흐름과 실제 배수구 방향은
        미확인입니다.
      </p>
      <p>
        지붕·포장면은 불투수 참조, 경지계는 공개 분류별 투수 참조 조건으로 비교합니다. 현장
        경사·재료·토양과 시공 적합성은 미확인입니다.
      </p>
      {!!site.referenceInfrastructure?.references.length && (
        <p>
          공개 시설 위치점 {site.referenceInfrastructure.references.length}개가 후보 안에 있습니다.
          실제 부지·수직 위치·운영 여부의 확인은 필요합니다.
        </p>
      )}
      <a
        href="https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT"
        target="_blank"
        rel="noreferrer"
      >
        EPA SWMM 입력·토양·조도 기준 ↗
      </a>
    </details>
  );
}
