import { runoffComparisonDto } from '../dto/runoffComparisonDto';
import { designContractDto } from '../dto/designContractDto';
import { physicalAmount as amount } from '../service/physicalValueFormat';
import './runoffComparison.css';
import { RelativeImprovement } from './RelativeImprovement';
const time = (v: string) =>
  new Date(v).toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
    timeZone: 'Asia/Seoul',
  });
export function RunoffComparison({ value, contract }: { value: unknown; contract?: unknown }) {
  const parsed = runoffComparisonDto.safeParse(value);
  if (!parsed.success) return <p role="status">이 기록의 유출 비교 자료를 확인하지 못했습니다.</p>;
  const result = parsed.data;
  const before = result.cases.find((c) => c.id === 'baseline')!;
  const after = result.cases.find((c) => c.id === 'strategy')!;
  const parsedContract = designContractDto.safeParse(contract);
  const design = parsedContract.success ? parsedContract.data : null;
  const sameWindow =
    design &&
    Date.parse(design.evaluation.start) === Date.parse(before.metrics.start) &&
    Date.parse(design.evaluation.end) === Date.parse(before.metrics.end);
  const rows = [
    ['유출·하부배수', before.dischargeM3, after.dischargeM3, 'm³'],
    ['시작 수분·저류', before.initialStorageM3, after.initialStorageM3, 'm³'],
    ['종료 수분·저류', before.finalStorageM3, after.finalStorageM3, 'm³'],
    ['순저류 변화', before.netStorageM3, after.netStorageM3, 'm³'],
    ['평가체적', before.accountedDischargeM3, after.accountedDischargeM3, 'm³'],
    ['출구 첨두', before.metrics.peakM3s, after.metrics.peakM3s, 'm³/s'],
  ] as const;
  return (
    <section className="runoff-comparison" aria-label="설치 전후 물 흐름 비교">
      <h4>설치 전후 물 흐름</h4>
      <p>
        {time(before.metrics.start)}–{time(before.metrics.end)} KST · 선행 기간 제외
      </p>
      {contract !== undefined &&
        (sameWindow ? (
          <p>
            평가 표면 {amount(design.spatial.evaluationSurfaceAreaM2)} m² · 시설 설치{' '}
            {amount(design.facility.areaM2)} m² · 시설에 직접 내리는 강우만 유입
            {design.flowGraph && ' · 배수 관망·지표 침수 격자 미연결'}
          </p>
        ) : (
          <p role="status">이 기록의 설계·평가 범위 근거를 확인하지 못했습니다.</p>
        ))}
      <div className="runoff-comparison-table">
        <table>
          <thead>
            <tr>
              <th>항목</th>
              <th>설치 전</th>
              <th>설치 후</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([title, a, b, unit]) => (
              <tr key={title}>
                <th>{title}</th>
                <td>
                  {amount(a)} <small>{unit}</small>
                </td>
                <td>
                  {amount(b)} <small>{unit}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(
        [
          ['평가체적 차이', 'surfaceAccountedVolumeM3', result.accountedReductionM3, 'm³'],
          ['유출·배수 차이', 'surfaceDischargeM3', result.dischargeReductionM3, 'm³'],
          ['선택 표면 첨두 차이', 'surfacePeakM3s', result.peakReductionM3s, 'm³/s'],
        ] as const
      ).map(([label, id, difference, unit]) => (
        <p key={id} className="runoff-comparison-change">
          {label} {amount(difference)} {unit}{' '}
          <RelativeImprovement metric={result.metricComparison?.metrics.find((m) => m.id === id)} />
        </p>
      ))}
      <p>
        차이는 설치 전에서 설치 후를 뺀 값이며 음수는 악화입니다. 개선율은 보조값이며 순위에
        사용하지 않습니다. 평가체적은 유출·배수에 순저류 변화를 더한 값이며, 남은 물을 영구 저감으로
        계산하지 않습니다.
      </p>
      <details>
        <summary>첨두 시각·물수지</summary>
        {[before, after].map((c) => (
          <p key={c.id}>
            {c.id === 'baseline' ? '설치 전' : '설치 후'} 첨두{' '}
            {c.metrics.peakAt ? time(c.metrics.peakAt) + ' KST' : '유출 없음'}
            {' · '}최대 내부 간격 {amount(c.metrics.maximumStepSeconds)}초 ·{' '}
            {c.metrics.stepCount.toLocaleString('ko-KR')}단계
            <br />
            강우 {amount(c.precipitationM3)} · 침투 {amount(c.infiltrationM3)} · 증발{' '}
            {amount(c.evaporationM3)} · 수지 잔차 {amount(c.balanceResidualM3)} m³
          </p>
        ))}
        <p>
          선택 표면 출구의 표면 유출과 하부배수를 같은 계산 단계에서 합산한 첨두입니다.
          하수관·하천이나 구 전체의 첨두가 아닙니다. 각 시설의 첨두를 합산하지 않습니다.
        </p>
        <p>
          시각은 내부 계산 구간의 종료 시각입니다. 원 계산값을 사용하며 1분 표시 기록으로 첨두를
          다시 구하지 않습니다.
        </p>
      </details>
    </section>
  );
}
