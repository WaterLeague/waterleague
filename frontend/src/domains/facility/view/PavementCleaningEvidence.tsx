import { useState } from 'react';
import { GameSelect } from '../../../shared/ui/GameSelect';
import type { CleaningPair } from '../dto/pavementCleaningDto';
import {
  cleaningComparison,
  cleaningMethods,
  cleaningObservations,
  type InfiltrationUnit,
} from '../service/pavementCleaningService';
import './pavement-cleaning.css';

const number = (value: number) => value.toLocaleString('ko-KR', { maximumFractionDigits: 4 });
const signed = (value: number) => `${value > 0 ? '+' : ''}${number(value)}`;

export function CleaningObservationTable({
  pair,
  unit,
}: {
  pair: CleaningPair;
  unit: InfiltrationUnit;
}) {
  const result = cleaningComparison(pair, unit);
  return (
    <>
      <p>
        {pair.site} · {pair.campaign} · {pair.location}
        <br />
        {cleaningMethods[pair.method]} {pair.passes}회 통과
      </p>
      <table>
        <caption>현장 표면 침투속도 · {unit}</caption>
        <thead>
          <tr>
            <th scope="col">측정 항목</th>
            <th scope="col">청소 전</th>
            <th scope="col">청소 후</th>
          </tr>
        </thead>
        <tbody>
          {(
            [
              ['median', '중앙값'],
              ['mean', '평균'],
              ['standardDeviation', '표준편차'],
            ] as const
          ).map(([key, label]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              <td>{number(result.before[key])}</td>
              <td>{number(result.after[key])}</td>
            </tr>
          ))}
          <tr>
            <th scope="row">최소–최대</th>
            {[result.before, result.after].map((v, i) => (
              <td key={i}>
                {number(v.min)}–{number(v.max)}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">시험 횟수</th>
            <td>{result.before.testCount}</td>
            <td>{result.after.testCount}</td>
          </tr>
        </tbody>
      </table>
      <p>
        중앙값 차이 {signed(result.medianDifference)} {unit} · 청소 전 대비{' '}
        {result.medianChangePercent === null ? '미산정' : `${signed(result.medianChangePercent)}%`}
      </p>
      <p>
        원문의 t 검정 p값 {number(pair.pValue)}
        {pair.pValue >= 0.05 && ' · 원문에서 통계적으로 뚜렷한 차이가 없었던 사례입니다.'}
      </p>
    </>
  );
}

export function PavementCleaningEvidence() {
  const [selected, setSelected] = useState('PINEY_WOOD_2014_NEAR');
  const [unit, setUnit] = useState<InfiltrationUnit>('mm/min');
  if (!cleaningObservations)
    return <p role="status">청소 전후 공개 측정 자료를 확인할 수 없습니다.</p>;
  const pair = cleaningObservations.pairs.find((v) => v.id === selected);
  if (!pair) return null;
  return (
    <details className="pavement-cleaning-evidence">
      <summary>청소 전후 현장 측정 사례</summary>
      <p>
        미국 맞물림 콘크리트 블록 포장(PICP)의 같은 시험 구역에서 측정한 전후 값입니다. 선택한 서울
        위치나 Type-A 블록의 청소 효과를 예측하는 값은 아닙니다.
      </p>
      <GameSelect
        label="청소 전후 시험 구역"
        value={selected}
        options={cleaningObservations.pairs.map((v) => ({
          value: v.id,
          label: `${v.site.split(' · ')[0]} · ${v.campaign} · ${v.location}`,
        }))}
        onChange={setSelected}
      />
      <GameSelect
        label="침투속도 표시 단위"
        value={unit}
        options={[
          { value: 'mm/min', label: 'mm/min · 원문 단위' },
          { value: 'mm/h', label: 'mm/h · 시간당 환산' },
        ]}
        onChange={(v) => setUnit(v === 'mm/h' ? 'mm/h' : 'mm/min')}
      />
      <div aria-live="polite" aria-atomic="true">
        <CleaningObservationTable pair={pair} unit={unit} />
      </div>
      <p>
        표면 침투시험값은 재료 투수계수와 다릅니다. 이 측정값을 계산 입력이나 점수에 적용하지
        않습니다. 시공 직후 동일 지점 값과 관리비가 없어 신설 대비 회복률·비용효율은 미산정입니다.
        범위는 실제 최소–최대이며 신뢰구간이 아닙니다.
      </p>
      <a href={cleaningObservations.source.url} target="_blank" rel="noreferrer">
        Winston 외 · 2016년 · 표 3 ↗
      </a>
    </details>
  );
}
