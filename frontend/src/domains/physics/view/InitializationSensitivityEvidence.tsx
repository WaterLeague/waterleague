import {
  initializationSensitivityDto,
  type InitializationSensitivityData,
  type SensitivityMetrics,
} from '../dto/initializationSensitivityDto';
import { InitializationEvidence } from './InitializationEvidence';
import { CisternInitializationEvidence } from './CisternInitializationEvidence';
import { physicalAmount as amount } from '../service/physicalValueFormat';
import './initializationSensitivity.css';

const metrics: {
  key: keyof SensitivityMetrics;
  label: string;
  unit: string;
  multiplier?: number;
}[] = [
  { key: 'initialSoilMoisture', label: '평가 시작 토양수분', unit: '%', multiplier: 100 },
  { key: 'initialStorageM3', label: '평가 시작 총저류', unit: 'm³' },
  { key: 'evaluatedDischargeM3', label: '평가 기간 유출·배수', unit: 'm³' },
  { key: 'evaluatedEvaporationM3', label: '증발산', unit: 'm³' },
  { key: 'evaluatedInfiltrationM3', label: '침투', unit: 'm³' },
  { key: 'peakDischargeMean1MinM3s', label: '1분 평균 첨두', unit: 'm³/s' },
  { key: 'contributionM3', label: '평가체적 감소', unit: 'm³' },
];

export function InitializationSensitivityEvidence({
  value,
}: {
  value: InitializationSensitivityData;
}) {
  const parsed = initializationSensitivityDto.safeParse(value);
  if (!parsed.success)
    return (
      <p role="status">
        시작 수분 비교 기록의 형식을 확인할 수 없습니다. 재현 자료에서 원본을 확인해 주세요.
      </p>
    );
  const report = parsed.data;
  if (report.schemaVersion === 3) return <CisternInitializationEvidence value={report} />;
  const swale = report.seedPolicy === 'NOT_APPLICABLE_FIXED_EMPTY_SURFACE';
  const seedLabel = (seed: number) =>
    swale ? '빈 표면 시작' : seed === 0 ? '건조 시작' : '포화 시작';
  const cases = [...report.cases].sort((a, b) => a.seedSaturationPercent - b.seedSaturationPercent);
  const complete = report.comparison.status === 'MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD';
  return (
    <section className="initialization-sensitivity" aria-label="시작 수분 비교 결과">
      <h4>{swale ? '선행 관측 이후의 식생수로 상태' : '시작 수분에 따른 차이'}</h4>
      <p>
        {report.cellId} · {amount(report.areaM2)} m².{' '}
        {swale
          ? '빈 표면과 엔진 기본 침투 상태에서 선행 7일 강우·기상을 계산했습니다.'
          : '같은 선행 7일 강우·기상과 시설 제원에 서로 다른 시작 상태를 적용했습니다.'}
      </p>
      <p>
        {swale
          ? '식생수로는 LID 초기 포화도가 적용되지 않습니다. 건습 비교는 해당 없으며, 표는 선행 7일 이후의 계산 상태입니다.'
          : '건조·포화는 선행 계산 전의 시드입니다. 표의 수분·저류는 7일이 지난 재해 평가 시작 상태입니다.'}
      </p>
      {!complete && (
        <p role="status">
          비교 미완료 · 일부 조건이 계산·물수지 검사를 통과하지 못했습니다. 실패를 0으로 처리하지
          않습니다.
        </p>
      )}
      <table>
        <caption>선행 7일 이후의 상태와 재해 기간 결과</caption>
        <thead>
          <tr>
            <th scope="col">계산 지표</th>
            {cases.map((c) => (
              <th scope="col" key={c.seedSaturationPercent}>
                {seedLabel(c.seedSaturationPercent)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map(({ key, label, unit, multiplier = 1 }) => (
            <tr key={key}>
              <th scope="row">
                {label}
                <small>{unit}</small>
              </th>
              {cases.map((c) => (
                <td key={c.seedSaturationPercent}>
                  {c.status === 'FAILED'
                    ? '계산 실패'
                    : c.metrics[key] === null
                      ? '해당 없음'
                      : amount(c.metrics[key] * multiplier)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!swale && report.comparison.status === 'MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD' && (
        <p>
          포화 시작의 평가체적 감소량이 건조 시작보다{' '}
          {amount(report.comparison.seedDifferences[0].wetMinusDry.contributionM3)} m³ 차이 납니다.
          음수는 감소 효과가 더 작다는 뜻입니다.
        </p>
      )}
      <p>
        {swale
          ? '단일 시작 상태이며 건습 시드의 수렴 검증이 아닙니다.'
          : '두 시작 조건의 차이이며 확률 신뢰구간이나 초기 상태의 수렴 판정이 아닙니다.'}{' '}
        일반 설계 결과와 순위에는 합산하지 않습니다.
      </p>
      <details>
        <summary>시작 조건과 원본 근거</summary>
        {cases.map((c) => (
          <div key={c.seedSaturationPercent}>
            <h5>
              {seedLabel(c.seedSaturationPercent)} ·{' '}
              {c.status === 'SUCCEEDED' ? '계산 완료' : '계산 실패'}
            </h5>
            {c.status === 'SUCCEEDED' && <InitializationEvidence value={c.initialization} />}
          </div>
        ))}
        {report.limitations.map((v) => (
          <p key={v}>{v}</p>
        ))}
        <p className="sensitivity-hash">입력 SHA-256 · {report.inputSha256}</p>
        <p>재현 자료의 sensitivity 폴더에 원 입력·조건별 계산 파일·실패 기록을 보관합니다.</p>
      </details>
    </section>
  );
}
