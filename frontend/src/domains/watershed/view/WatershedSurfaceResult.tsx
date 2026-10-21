import type { WatershedSurfaceComparison } from '../dto/watershedSurfaceDto';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
const rawAmount = (value: number) =>
  value !== 0 && Math.abs(value) < 0.00001
    ? physicalAmount(value)
    : value.toLocaleString('ko-KR', { maximumFractionDigits: 6 });

export function WatershedSurfaceResult({ result }: { result: WatershedSurfaceComparison }) {
  const [baseline, strategy] = result.cases;
  const rows = [
    ['outwardVolumeM3', '두 출구의 총 방류량', 'm³'],
    ['peakOutwardM3s', '동시 출구 유량의 최댓값', 'm³/s'],
    ['maximumDepthM', '구역 내 최대 수심', 'm'],
    ['maximumWetAreaM2', '최대 침수 면적', 'm²'],
    ['maximumWetDurationSeconds', '가장 오래 젖은 격자의 시간', '초'],
    ['depthAreaTimeM3Hours', '수심·면적·시간 누적량', 'm³·h'],
  ] as const;
  return (
    <section className="watershed-surface-result" aria-label="지표·관망 결합 비교">
      <h4>지표 수심과 출구 유량 비교</h4>
      <p>
        같은 공개 지형·강우·외부 유입으로 두 설계를 계산했습니다. 침수 면적·시간은 수심 1cm 초과
        기준입니다.
      </p>
      <p className="watershed-warning">
        폐쇄한 계산 구역과 높이 기준 가정의 결과입니다. 실제 침수지도·피해 감소로 해석할 수
        없습니다.
      </p>
      <p>
        전체 물수지 잔차: 기준안 {physicalAmount(baseline.balance.balanceResidualM3)}m³ · 설계안{' '}
        {physicalAmount(strategy.balance.balanceResidualM3)}m³. 각 계산의 잔차이며 효과 차이의 오차
        추정치는 아닙니다. 수치 검증 통과만으로 작은 개선량의 유의성이 입증되지는 않습니다.
      </p>
      {result.numericalStatus === 'FAILED' && (
        <p role="status">수치 검증 실패 · 원 결과는 보존하고 개선량은 보류합니다.</p>
      )}
      <div
        className="watershed-table-scroll"
        role="region"
        aria-label="결합 비교 지표 표"
        tabIndex={0}
      >
        <table>
          <caption>
            양수 개선량은 감소, 음수는 증가 · 평가 기간 {physicalAmount(baseline.durationSeconds)}초
          </caption>
          <thead>
            <tr>
              <th>지표</th>
              <th>기준안</th>
              <th>설계안</th>
              <th>감소량</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, label, unit]) => (
              <tr key={key}>
                <th scope="row">
                  {label} ({unit})
                </th>
                <td>{rawAmount(baseline.raw[key])}</td>
                <td>{rawAmount(strategy.raw[key])}</td>
                <td>
                  {result.signedReduction ? physicalAmount(result.signedReduction[key]) : '보류'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>계산 조건과 한계</summary>
        <p>
          유출 계산 간격 {result.parameters.networkNumericalProfile.options.WET_STEP ?? 300}초 ·
          기준안과 설계안 동일 적용
        </p>
        {result.limitations.map((text) => (
          <p key={text}>{text}</p>
        ))}
        <p>
          기준안 관망 수지 오차 {physicalAmount(baseline.networkRoutingContinuityPercent)}% · 설계안{' '}
          {physicalAmount(strategy.networkRoutingContinuityPercent)}%
        </p>
        <p>원 자료와 교환 원장, 재생 코드는 아래 재현 자료에 포함됩니다.</p>
      </details>
    </section>
  );
}
