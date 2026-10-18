import type { WatershedCostSnapshot } from '../dto/watershedCostDto';
import { networkNames } from '../service/watershedDesign';
const won = (v: number) => `${v.toLocaleString('ko-KR')}원`;
export function WatershedCosts({
  costing,
  preview = false,
  additionalUnpriced = [],
}: {
  costing: WatershedCostSnapshot;
  preview?: boolean;
  additionalUnpriced?: { id: string; name: string }[];
}) {
  return (
    <section
      className="watershed-costs"
      aria-label={preview ? '설계 참고 공사비 미리보기' : '저장된 참고 공사비'}
    >
      <h3>{preview ? '설계 참고 공사비' : '저장된 참고 공사비'}</h3>
      <p>{costing.source.year}년 진주 사업계획 · 현재 서울 견적 아님</p>
      <strong>
        {costing.knownReferenceSubtotalKrw === null
          ? '산정 가능한 참고 금액 없음'
          : `산정된 항목만 ${won(costing.knownReferenceSubtotalKrw)}`}
      </strong>
      <p>
        미산정 시설 {costing.unpricedPlacementIds.length + additionalUnpriced.length}곳 · 전체
        설치비 미확정 · 게임 예산 차감 없음
      </p>
      <ul>
        {additionalUnpriced.map(({ id, name }) => (
          <li key={id}>
            <span>
              {id} · {name}
            </span>
            <strong>미산정</strong>
            <p>현장 부지·굴착·접속 공종과 규격 일치 단가 미확인</p>
          </li>
        ))}
        {costing.items.map((i) => (
          <li key={i.placementId}>
            <span>
              {i.placementId} ·{' '}
              {networkNames[i.facilityType as keyof typeof networkNames] ?? i.facilityType} ·{' '}
              {i.areaM2.toLocaleString('ko-KR')} m²
            </span>
            <strong>
              {i.referenceAmountKrw === null
                ? '미산정'
                : `${won(i.referenceAmountKrw)} · 면적 외삽 참고`}
            </strong>
            <details>
              <summary>단가 적용 근거</summary>
              {i.notes.map((n, index) => (
                <p key={index}>{n}</p>
              ))}
            </details>
          </li>
        ))}
      </ul>
      <details>
        <summary>공개 원문·비용 적용 범위</summary>
        <a href={costing.source.url} target="_blank" rel="noreferrer">
          {costing.source.title} · PDF {costing.source.pdfPages.join('·')}쪽
        </a>
        {costing.limitations.map((n, index) => (
          <p key={index}>{n}</p>
        ))}
      </details>
      {preview && (
        <small>계산 요청 시 서버가 같은 단가·수량을 검증해 원가 기록을 고정합니다.</small>
      )}
    </section>
  );
}
