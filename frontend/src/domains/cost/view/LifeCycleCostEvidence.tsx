import { lifeCycleCostDto } from '../dto/lifeCycleCostDto';
import { lifeCycleMoney as format } from '../service/lifeCycleMoney';
const labels: Record<string, string> = {
  INITIAL: '초기 설치',
  OPERATION: '운전·점검',
  INSPECTION_CLEANING: '청소',
  REPAIR: '수선',
  REPLACEMENT: '교체',
  DISPOSAL: '철거·처분',
  RESIDUAL: '잔존가치',
};
const missingLabels: Record<string, string> = {
  STUDY_PERIOD_MISSING: '평가기간',
  DISCOUNT_RATES_MISSING: '할인율',
  PRICE_BASE_YEAR_MISSING: '가격 기준연도',
  FUNCTIONAL_UNIT_UNVERIFIED: '규격·공사 범위 일치',
};
export function LifeCycleCostEvidence({ value }: { value: unknown }) {
  const parsed = lifeCycleCostDto.safeParse(value);
  if (!parsed.success)
    return <p className="micro-note">생애주기비용 기록의 형식을 확인하지 못했습니다.</p>;
  const report = parsed.data;
  return (
    <>
      <p>
        <strong>
          {report.lifeCycleCost === null
            ? '전체 생애주기비용 미산정'
            : `생애주기비용 ${format(report.lifeCycleCost, report.currency)}`}
        </strong>
      </p>
      {report.status === 'PARTIAL' && report.knownPresentValue !== null && (
        <p>
          문헌 금액·가정에 따른 {report.studyPeriodYears}년 부분 현재가치{' '}
          {format(report.knownPresentValue, report.currency)} · 전체 공사비와 경제성 순위 아님
        </p>
      )}
      <p>
        미확인:{' '}
        {report.missingInputs
          .map((k) => missingLabels[k] ?? labels[k.replace('INCOMPLETE_', '')] ?? '추가 비용 근거')
          .join(' · ') || '없음'}
      </p>
      <p>설치 예산·물리 점수와 별도입니다. 사건 효과를 연간·생애 효과로 환산하지 않습니다.</p>
      {report.studyPeriodYears !== null && (
        <details>
          <summary>평가기간·할인 가정·연차별 비용</summary>
          <p>
            {report.studyPeriodYears}년 ·{' '}
            {report.priceBaseYear === null
              ? '가격 기준연도 미확인'
              : `${report.priceBaseYear}년 가격`}{' '}
            ·{' '}
            {report.discountKind === 'REAL'
              ? '실질'
              : report.discountKind === 'NOMINAL'
                ? '명목'
                : '미확인'}{' '}
            할인율{' '}
            {report.discountRates && new Set(report.discountRates).size === 1
              ? `${(Number(report.discountRates[0]) * 100).toLocaleString('ko-KR')}%`
              : '연차별 적용'}
          </p>
          <dl className="watershed-parameters">
            {report.categories.map((c) => (
              <div key={c.id}>
                <dt>{labels[c.id]}</dt>
                <dd>
                  {c.presentValue === null
                    ? '미산정'
                    : c.coverage === 'NOT_APPLICABLE'
                      ? '해당 없음 · 근거 기록'
                      : format(c.presentValue, report.currency)}
                </dd>
              </div>
            ))}
          </dl>
          {report.sensitivity?.map((s) => (
            <p key={s.id}>
              {s.label} {Number(s.rate) * 100}% · 부분 현재가치{' '}
              {s.knownPresentValue === null
                ? '미산정'
                : format(s.knownPresentValue, report.currency)}
            </p>
          ))}
          <details>
            <summary>연차별 현금흐름</summary>
            <div className="watershed-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>연차</th>
                    <th>비용</th>
                    <th>잔존가치</th>
                    <th>현재가치</th>
                  </tr>
                </thead>
                <tbody>
                  {report.annualCashflows.map((c) => (
                    <tr key={c.year}>
                      <td>{c.year}</td>
                      <td>{format(c.cost, report.currency)}</td>
                      <td>{format(c.credit, report.currency)}</td>
                      <td>{format(c.presentValue, report.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p>
            연말 비용 기준 · 합산 후 소수 둘째 자리 반올림 · 항목별 표시 합과의 차이{' '}
            {report.categoryRoundingDifference === null
              ? '미산정'
              : format(report.categoryRoundingDifference, report.currency)}
          </p>
          {report.limitations.map((text) => (
            <p key={text}>{text}</p>
          ))}
        </details>
      )}
    </>
  );
}
