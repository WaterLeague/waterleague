import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Download, RotateCcw, Trophy } from 'lucide-react';
import type { Job, Lab, Version } from '../entity/game';
import { facilities, format, won } from '../service/gameService';
import { Hydrograph } from './Hydrograph';
import { rainDate } from './RainfallSelector';
import { StormReplay } from './StormReplay';
import type { CandidateMap } from '../../catalog/entity/catalog';

export function RoundReport({
  job,
  lab,
  evaluated,
  map,
  current,
  busy,
  league,
  onRetry,
  onSubmit,
  onBoard,
}: {
  job: Job;
  lab: Lab;
  evaluated: Version | null;
  map: CandidateMap | null;
  current: boolean;
  busy: boolean;
  league: boolean;
  onRetry: () => void;
  onSubmit: () => void;
  onBoard: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [view, setView] = useState<'summary' | 'replay'>('summary');
  useEffect(() => {
    heading.current?.focus();
  }, [job.id]);
  const result = job.result;
  if (!result) return null;
  const reduced = result.baseline.accountedDischargeM3 - result.strategy.accountedDischargeM3;
  return (
    <section className="round-report" aria-label="이번 도전 결과">
      <header className="round-report-heading">
        <span>ROUND RESULT / 서버 계산 완료</span>
        <span>
          {rainDate(lab.model.rainfall.start)} · {lab.model.rainfall.stationName} ·{' '}
          {lab.model.rainfall.totalDepthMm} mm
        </span>
      </header>
      {!current && (
        <p className="round-stale" role="status">
          현재 배치가 계산한 버전과 다릅니다. 이 화면의 결과·제출 대상은 이전에 계산한 배치입니다.
        </p>
      )}
      <div className="round-view-nav" role="group" aria-label="계산 결과 보기">
        <button aria-pressed={view === 'summary'} onClick={() => setView('summary')}>
          결과 요약
        </button>
        <button aria-pressed={view === 'replay'} onClick={() => setView('replay')}>
          시간별 재생 <ArrowRight size={15} />
        </button>
        <span>
          최종 탐색 점수 <b>{format.format(result.score)}점</b>
        </span>
      </div>
      {view === 'replay' ? (
        <StormReplay job={job} lab={lab} evaluated={evaluated} map={map} />
      ) : (
        <div className="round-report-overview">
          <div className="round-score">
            <span>계산한 설계의 탐색 점수</span>
            <h1 ref={heading} tabIndex={-1}>
              {format.format(result.score)}
              <small>점</small>
            </h1>
            <p>
              {reduced > 0
                ? '시설이 없는 기준안보다\n초기저류를 보정한 평가량이 줄었습니다.'
                : reduced < 0
                  ? '시설이 없는 기준안보다\n초기저류를 보정한 평가량이 늘었습니다.'
                  : '시설이 없는 기준안과\n초기저류를 보정한 평가량이 같습니다.'}
            </p>
            <strong>
              {format.format(Math.abs(reduced))} m³{' '}
              <small>{reduced > 0 ? '감소' : reduced < 0 ? '증가' : '차이'}</small>
            </strong>
            <p className="round-scope">
              모델 안의 계산 결과 · 현장 효과 미검증
              <br />
              유출과 마지막 남은 물을 함께 평가하고, 시작 전에 있던 물은 제외합니다.
            </p>
          </div>
          <div className="round-comparison">
            <h2>무엇이 달라졌나요?</h2>
            <table>
              <thead>
                <tr>
                  <th scope="col">계산 항목</th>
                  <th scope="col">시설 없음</th>
                  <th scope="col">계산한 설계</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">
                    기간 유출 <small>m³</small>
                  </th>
                  <td>{format.format(result.baseline.runoffM3)}</td>
                  <td>{format.format(result.strategy.runoffM3)}</td>
                </tr>
                <tr>
                  <th scope="row">
                    최종 잔여저류 <small>m³</small>
                  </th>
                  <td>{format.format(result.baseline.finalStorageM3)}</td>
                  <td>{format.format(result.strategy.finalStorageM3)}</td>
                </tr>
                <tr>
                  <th scope="row">
                    초기저류 · 차감 <small>m³</small>
                  </th>
                  <td>{format.format(result.baseline.initialStorageM3)}</td>
                  <td>{format.format(result.strategy.initialStorageM3)}</td>
                </tr>
                <tr className="round-total">
                  <th scope="row">
                    보정 평가량 <small>m³</small>
                  </th>
                  <td>{format.format(result.baseline.accountedDischargeM3)}</td>
                  <td>{format.format(result.strategy.accountedDischargeM3)}</td>
                </tr>
              </tbody>
            </table>
            <Hydrograph job={job} rainfall={lab.model.rainfall} designLabel="계산한 설계" />
          </div>
        </div>
      )}
      <div className="round-actions">
        <button className="challenge-start" onClick={onRetry}>
          <RotateCcw size={18} /> 배치 수정·재도전 <ArrowRight size={18} />
        </button>
        <button className="outline-button" disabled={busy} onClick={onSubmit}>
          <Trophy size={17} /> {league ? '리그 규칙·제출로 이동' : '이 계산 기록 제출'}
        </button>
        <button className="text-button" onClick={onBoard}>
          기록 경쟁 보기 <ArrowRight size={15} />
        </button>
      </div>
      <details className="round-details">
        <summary>계산한 배치·품질·재현 자료</summary>
        <div className="round-details-grid">
          <div>
            <h3>
              저장 버전 {evaluated?.revision ?? '—'} ·{' '}
              {evaluated ? won(evaluated.cost) : '비용 확인 불가'}
            </h3>
            <ul>
              {evaluated?.placements.map((p) => (
                <li key={p.cellId}>
                  <b>{p.cellId}</b> {facilities[p.facilityType].name} · {format.format(p.areaM2)} m²
                </li>
              ))}
            </ul>
            {!evaluated?.placements.length && <p>설치 시설 없음</p>}
          </div>
          <div>
            <p>물수지 오차 {format.format(result.strategy.runoffContinuityPercent)}%</p>
            <p>
              가정 변화 점수{' '}
              {format.format(Math.min(result.score, ...result.sensitivity.map((s) => s.score)))} ~{' '}
              {format.format(Math.max(result.score, ...result.sensitivity.map((s) => s.score)))}점.
              투수계수 가정 비교이며 신뢰구간이 아닙니다.
            </p>
            <p>
              {result.execution?.mode === 'REUSED'
                ? '동일 입력의 서버 계산을 재사용했습니다. 독립 검증이 아닙니다.'
                : '서버에서 SWMM으로 계산했습니다.'}
            </p>
            <a className="text-button" href={`/api/v1/simulations/${job.id}/bundle`}>
              <Download size={15} /> 입력·결과 재현 묶음
            </a>
          </div>
        </div>
      </details>
    </section>
  );
}
