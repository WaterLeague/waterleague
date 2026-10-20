import {
  pavementMaintenanceDto,
  type PavementMaintenanceComparison,
} from '../dto/pavementMaintenanceDto';
import { physicalAmount as amount } from '../../physics/service/physicalValueFormat';
import type { SensitivityMetrics } from '../../physics/dto/initializationSensitivityDto';
import { PavementCleaningEvidence } from './PavementCleaningEvidence';
import '../../physics/view/initializationSensitivity.css';

const labels = { FRESH: '새 블록', DUST_96_G: '협잡물 96g', DUST_192_G: '협잡물 192g' };
const metrics: { key: keyof SensitivityMetrics; label: string; unit: string }[] = [
  { key: 'initialStorageM3', label: '평가 시작 저류량', unit: 'm³' },
  { key: 'evaluatedDischargeM3', label: '기간 유출·배수', unit: 'm³' },
  { key: 'evaluatedInfiltrationM3', label: '기간 침투량', unit: 'm³' },
  { key: 'peakDischargeMean1MinM3s', label: '1분 평균 첨두', unit: 'm³/s' },
  { key: 'contributionM3', label: '평가체적 감소', unit: 'm³' },
];

export function PavementMaintenanceEvidence({ value }: { value: PavementMaintenanceComparison }) {
  const parsed = pavementMaintenanceDto.safeParse(value);
  if (!parsed.success)
    return <p role="status">막힘 비교 기록을 확인할 수 없습니다. 재현 자료를 확인해 주세요.</p>;
  const report = parsed.data;
  return (
    <section className="initialization-sensitivity" aria-label="투수포장 막힘 조건 비교">
      <h4>같은 강우에서의 투수포장 막힘 비교</h4>
      <p>
        선택 면적 {amount(report.areaM2)} m²에 공개 실험의 재료 조건을 적용했습니다. 협잡물 양은
        실험 시료 4장, 0.16 m² 기준입니다.
      </p>
      <p>
        포장 두께 60mm와 공극률 20%를 고정하고 투수값만 비교합니다. 각 조건에서 선행 7일 강우를
        재생한 뒤 사건 전체를 계산합니다.
      </p>
      {report.status === 'INCOMPLETE' && (
        <p role="status">비교 미완료 · 일부 조건의 계산 또는 물수지 검사 실패</p>
      )}
      <table>
        <caption>문헌 재료 조건별 계산 결과</caption>
        <thead>
          <tr>
            <th scope="col">항목</th>
            {report.cases.map((c) => (
              <th scope="col" key={c.scenario.id}>
                {labels[c.scenario.id]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">
              적용 투수값<small>mm/h</small>
            </th>
            {report.cases.map((c) => (
              <td key={c.scenario.id}>{amount(c.scenario.conductivityMmH)}</td>
            ))}
          </tr>
          {metrics.map(({ key, label, unit }) => (
            <tr key={key}>
              <th scope="row">
                {label}
                <small>{unit}</small>
              </th>
              {report.cases.map((c) => (
                <td key={c.scenario.id}>
                  {c.status === 'FAILED'
                    ? '계산 실패'
                    : c.metrics[key] === null
                      ? '해당 없음'
                      : amount(c.metrics[key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        실제 사용 연수나 청소 효과를 예측하지 않습니다. 이 Type-A 블록의 청소 후 회복은 근거
        미확보로 미산정입니다. 현재 설치 설계의 비용·효과·순위에는 합산하지 않습니다.
      </p>
      <details>
        <summary>실험 조건과 출처</summary>
        {report.limitations.map((note) => (
          <p key={note}>{note}</p>
        ))}
        <a href={report.source.url} target="_blank" rel="noreferrer">
          {report.source.title} · 표 7–9 ↗
        </a>
        <code className="hash-value">입력 SHA-256: {report.inputSha256}</code>
        <code className="hash-value">문헌 SHA-256: {report.source.sha256}</code>
      </details>
      <PavementCleaningEvidence />
    </section>
  );
}
