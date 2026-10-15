import type { ResearchEntry, ResearchDetail } from '../entity/research';
import { isPareto } from '../service/paretoService';
import { format, won } from '../../game/service/gameService';
import type { Metrics } from '../../game/entity/game';
export function CostPerformance({
  entries,
  onSelect,
}: {
  entries: ResearchEntry[];
  onSelect: (id: string) => void;
}) {
  if (!entries.length) return null;
  const maxCost = Math.max(...entries.map((e) => e.cost), 1),
    minScore = Math.min(0, ...entries.map((e) => e.score)),
    maxScore = Math.max(...entries.map((e) => e.score), minScore + 1);
  return (
    <section className="cost-performance">
      <h2>비용과 성능을 함께 비교</h2>
      <p className="micro-note">
        공유된 최대 100건 비교. 진한 점은 비용이 같거나 낮고 점수가 같거나 높으면서 둘 중 하나가 더
        나은 다른 기록이 없는 후보입니다. 비용은 참고 단가, 점수는 탐색 모델 기준입니다.
      </p>
      <svg viewBox="0 0 600 220" role="img" aria-label="추정 비용과 탐색 점수 비교">
        <path d="M50 15V180H580" fill="none" stroke="#bdcdb3" />
        <text x="50" y="209">
          0원
        </text>
        <text x="580" y="209" textAnchor="end">
          {won(maxCost)}
        </text>
        <text x="10" y="20">
          {format.format(maxScore)}
        </text>
        <text x="10" y="180">
          {format.format(minScore)}
        </text>
        {entries.map((e) => (
          <circle
            key={e.jobId}
            cx={50 + (e.cost / maxCost) * 520}
            cy={180 - ((e.score - minScore) / (maxScore - minScore)) * 155}
            r="6"
            fill={isPareto(e, entries) ? '#365f3b' : '#b4c7a6'}
            tabIndex={0}
            role="button"
            aria-label={`${won(e.cost)}, ${format.format(e.score)}점 기록 열기`}
            onClick={() => onSelect(e.jobId)}
            onKeyDown={(k) => {
              if (k.key === 'Enter' || k.key === ' ') {
                k.preventDefault();
                onSelect(e.jobId);
              }
            }}
          >
            <title>
              {won(e.cost)} · {format.format(e.score)}점
            </title>
          </circle>
        ))}
      </svg>
    </section>
  );
}
export function MetricsComparison({ detail }: { detail: ResearchDetail }) {
  const result = detail.simulation.result;
  if (!result) return null;
  const rows: [string, keyof Metrics][] = [
    ['강우 입력', 'precipitationM3'],
    ['기간 유출', 'runoffM3'],
    ['침투', 'infiltrationM3'],
    ['증발', 'evaporationM3'],
    ['초기 저류', 'initialStorageM3'],
    ['최종 잔여저류', 'finalStorageM3'],
    ['평가체적', 'accountedDischargeM3'],
  ];
  return (
    <section>
      <h3>물의 이동 · m³</h3>
      <table className="metrics-table">
        <thead>
          <tr>
            <th>항목</th>
            <th>시설 없음</th>
            <th>제출 설계</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, key]) => (
            <tr key={key}>
              <th>{label}</th>
              <td>{format.format(result.baseline[key] as number)}</td>
              <td>{format.format(result.strategy[key] as number)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="micro-note">
        물수지 오차 {format.format(result.strategy.runoffContinuityPercent)}% · 추정 비용{' '}
        {detail.version.currency === 'KRW' ? won(detail.version.cost) : '단위 미기록 (구버전)'} ·
        서버 버전 {detail.version.revision}
      </p>
      <h3>투수계수 가정별 점수</h3>
      <div className="placement-table">
        {result.sensitivity.map((s) => (
          <p key={s.conductivityFactor}>
            <b>기본값 × {s.conductivityFactor}</b>
            <span>{format.format(s.score)}점</span>
          </p>
        ))}
      </div>
      <p className="micro-note">
        이 범위는 확률적 신뢰구간이 아닙니다. 모델 {detail.simulation.modelHash.slice(0, 16)}… ·
        엔진 {result.engine.version}
      </p>
    </section>
  );
}
