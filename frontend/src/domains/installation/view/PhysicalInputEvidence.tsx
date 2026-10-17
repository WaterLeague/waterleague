import type { SharedSite } from '../entity/installation';
const number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 });
export function PhysicalInputEvidence({ site }: { site: SharedSite }) {
  const p = site.physicalInputs;
  if (!p) return null;
  return (
    <details className="budget-evidence">
      <summary>이 위치의 물리 계산 입력</summary>
      <dl className="physical-input-values">
        <dt>도형 기반 유출 폭</dt>
        <dd>{number.format(p.runoffWidthM)} m</dd>
        <dt>도형 장축 길이</dt>
        <dd>{number.format(p.flowLengthM)} m</dd>
        <dt>경사</dt>
        <dd>
          {number.format(p.slopePercent)}% ·{' '}
          {p.slopeMethod === 'NGII_2025_90M_HORN_TERRAIN_PROXY'
            ? '공개 DEM 산정'
            : '자료 미확보·설계값'}
        </dd>
        <dt>포장·지붕 재질</dt>
        <dd>{p.surfaceTag ?? '태그 미확보'}</dd>
        {p.nImpervious !== undefined && (
          <>
            <dt>표면 조도</dt>
            <dd>{p.nImpervious} · 재질별 문헌값</dd>
          </>
        )}
        {site.kind === 'GROUND' && (
          <>
            <dt>심토토성</dt>
            <dd>{p.soilClass ?? '단일 토성 확인 불가'}</dd>
          </>
        )}
        {p.conductivityMmH !== undefined && (
          <>
            <dt>원지반 투수계수</dt>
            <dd>{number.format(p.conductivityMmH)} mm/h · 토성군 문헌 추정</dd>
          </>
        )}
      </dl>
      <p>유출 폭은 면적을 도형 장축으로 나눈 값입니다. 실제 배수구 방향은 확인되지 않았습니다.</p>
      {p.slopeMethod === 'NGII_2025_90M_HORN_TERRAIN_PROXY' && (
        <p>
          2025 국토지리정보원 90m DEM의 지역 경사입니다. 개별 포장면의 실측 경사나 옥상 경사가
          아닙니다.
        </p>
      )}
      {p.conductivityRangeMmH && (
        <p>
          토성군 문헌 범위 {p.conductivityRangeMmH.map((v) => number.format(v)).join('–')} mm/h 중
          낮은 값으로 계산합니다. 도시 성토·다짐 상태와 시공 재료는 별도입니다.
        </p>
      )}
      <p>
        기준 표면 불투수율 100%는 선택한 옥상·포장면의 모델 조건이며 서울 전체의 비율이 아닙니다.
      </p>
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
