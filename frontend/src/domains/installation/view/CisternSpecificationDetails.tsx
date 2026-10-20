import type { CisternSpecification } from '../../facility/dto/cisternSpecificationDto';
export function CisternSpecificationDetails({
  specification: s,
}: {
  specification: CisternSpecification;
}) {
  const d = s.equipmentDimensionsM,
    p = s.procurement;
  return (
    <details className="cistern-specification-details">
      <summary>공개 규격 · 공사 범위</summary>
      <p>
        {s.material} · 길이 {d.length} × 폭 {d.width} × 높이 {d.height}m
      </p>
      <p>
        {s.declaredCapacity} · 명목 {s.nominalCapacityM3}m³. 외형 안의 실제 저류 단면과 유효 용량은
        미확인입니다.
      </p>
      <p>
        {p.basisMonth} 발주 예산 {p.grossKrw.toLocaleString('ko-KR')}원 (부가세 포함). 확정 설치비와
        게임 예산으로 사용하지 않습니다.
      </p>
      <p>공고 범위: {p.scope.join(' · ')}</p>
      <ul>
        {[...p.limitations, ...s.limitations].map((v) => (
          <li key={v}>{v}</li>
        ))}
      </ul>
      {s.sources.map((source) => (
        <p key={source.sha256}>
          <a href={source.url} target="_blank" rel="noreferrer">
            {source.title}
          </a>{' '}
          · {source.pages.join(', ')}쪽
        </p>
      ))}
    </details>
  );
}
