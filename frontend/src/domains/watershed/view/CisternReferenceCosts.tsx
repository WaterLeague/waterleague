import { useState } from 'react';
import type { CisternCostSnapshot } from '../dto/cisternCostDto';
const won = (n: number) => `${n.toLocaleString('ko-KR')}원`;
const labels = { BARREL: '물통', PIPE: '배관', PUMP: '펌프', LOG: '원문 Log 항목', ETC: '기타' };
const annualLabels = {
  ELECTRICITY: '전기요금 가정',
  MONITORING: '모니터링 가정',
  REPAIR_LABOUR_ETC: '보수·인건비 가정',
  CLEANING: '청소 가정',
};
export function CisternReferenceCosts({
  costing,
  preview = false,
}: {
  costing: CisternCostSnapshot;
  preview?: boolean;
}) {
  const [selected, setSelected] = useState('A');
  return (
    <section className="watershed-costs" aria-label="빗물이용조 공개 견적 비교">
      <h3>{preview ? '빗물이용조 참고 견적' : '저장된 빗물이용조 견적'}</h3>
      <p>{costing.source.publicationYear}년 발표 · 견적 기준일 미확인 · 현재 서울 가격 아님</p>
      <p>총용량만 맞춘 별도 견적입니다. 물통 개수·단면·배관·펌프 규격 일치는 미확인입니다.</p>
      <label>
        비교할 원문 견적
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          aria-label="빗물이용조 비교 견적"
        >
          {['A', 'B', 'C'].map((id) => (
            <option key={id} value={id}>
              업체 {id} · 원문 표 9
            </option>
          ))}
        </select>
      </label>
      {costing.items.map((item) => {
        const quote = item.quotes.find((q) => q.id === selected);
        return (
          <div className="watershed-facility-state" key={item.placementId}>
            <strong>
              {item.placementId} · 설계{' '}
              {item.capacityM3.toLocaleString('ko-KR', { maximumFractionDigits: 4 })} m³
            </strong>
            {!quote ? (
              <p>
                2.35 m³ 규격의 정수배와 불일치하거나 비교 범위(256개)를 초과하여 미산정. 임의 용량
                환산 없음.
              </p>
            ) : (
              <>
                <p>2.35 m³ 견적 {item.equivalentUnits}개분 · 시뮬레이션 물통 개수와 별개</p>
                <strong>견적 합계 {won(quote.quotedSubtotalKrw)}</strong>
                <p>
                  공개 3건 범위 {won(Math.min(...item.quotes.map((q) => q.quotedSubtotalKrw)))}~
                  {won(Math.max(...item.quotes.map((q) => q.quotedSubtotalKrw)))}
                </p>
                <details>
                  <summary>자재 내역·연간 비용 가정</summary>
                  <dl className="watershed-parameters">
                    {Object.entries(quote.components).map(([k, v]) => (
                      <div key={k}>
                        <dt>{labels[k as keyof typeof labels]}</dt>
                        <dd>{v === null ? '원문 미기재' : won(v)}</dd>
                      </div>
                    ))}
                    <div>
                      <dt>자재 소계</dt>
                      <dd>{won(quote.materialsKrw)}</dd>
                    </div>
                    <div>
                      <dt>총액과 자재 소계의 미분류 차액</dt>
                      <dd>{won(quote.unclassifiedDifferenceKrw)}</dd>
                    </div>
                  </dl>
                  <p>
                    연간 유지비 가정 {won(quote.annualEstimateKrw)}/년 · 실제 전력·운전량 계산 아님
                  </p>
                  <dl className="watershed-parameters">
                    {Object.entries(quote.annualComponentsKrw).map(([k, v]) => (
                      <div key={k}>
                        <dt>{annualLabels[k as keyof typeof annualLabels]}</dt>
                        <dd>{won(v)}/년</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </>
            )}
          </div>
        );
      })}
      <p>전체 설치비 미확정 · 다른 참고 부분합과 자동 합산 없음 · 게임 예산 차감 없음</p>
      <details>
        <summary>출처·견적 적용 범위</summary>
        <a href={costing.source.url} target="_blank" rel="noreferrer">
          {costing.source.title} · {costing.source.reference}
        </a>
        <p>
          <a href={costing.source.licenceUrl} target="_blank" rel="noreferrer">
            {costing.source.licence}
          </a>{' '}
          · 견적 금액 및 항목 추출·수량 환산
        </p>
        {costing.limitations.map((text, i) => (
          <p key={i}>{text}</p>
        ))}
      </details>
      {preview && (
        <small>
          세 견적을 모두 서버 기록에 보존합니다. 위 선택은 표시 전환이며 물리 계산을 바꾸지
          않습니다.
        </small>
      )}
    </section>
  );
}
