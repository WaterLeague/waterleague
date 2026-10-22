import { useEffect, useRef, useState } from 'react';
import { ChartNoAxesCombined, Sparkles } from 'lucide-react';
import { errorMessage } from '../../../shared/exception/ApiError';
import { facilities } from '../../game/service/gameService';
import type { FacilityType } from '../../game/entity/game';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
import {
  generateGameSummary,
  loadGameAnalysis,
  type GameAnalysis,
  type GameSummary,
} from '../repository/gameAnalysisRepository';
import './game-analysis.css';

const evidenceNames = {
  participation: '참여 현황',
  facilities: '시설 구성',
  districts: '구별 분포',
  activity: '활동 추이',
  scores: '점수 분포',
};
const statusNames: Record<string, string> = {
  IN_PROGRESS: '진행 중',
  PROVISIONAL: '최종 계산 중',
  WITHHELD: '비교 보류',
  FINAL: '최종 결과',
  EMPTY: '기록 없음',
  UPCOMING: '개최 예정',
  CANCELLED: '취소',
  RECORDED: '제출 기록',
};
type Measure = GameAnalysis['facts']['facilities'][number];

function Bars({ rows, label }: { rows: Measure[]; label: string }) {
  const maximum = Math.max(1, ...rows.map((r) => r.count));
  return rows.length ? (
    <ul className="analysis-bars" aria-label={label}>
      {rows.map((r) => (
        <li key={r.key}>
          <span>{r.label}</span>
          <strong>
            {r.count.toLocaleString()}
            <small>개</small>
          </strong>
          <div className="analysis-bar-track" aria-hidden="true">
            <i style={{ width: `${(r.count / maximum) * 100}%` }} />
          </div>
          <small>{r.areaM2.toLocaleString('ko-KR', { maximumFractionDigits: 2 })} m²</small>
        </li>
      ))}
    </ul>
  ) : (
    <p className="analysis-empty">시설 기록이 없습니다.</p>
  );
}

function ActivityChart({ rows, noun }: { rows: GameAnalysis['facts']['activity']; noun: string }) {
  if (!rows.length) return <p className="analysis-empty">활동 기록이 없습니다.</p>;
  const start = Date.parse(rows[0].day),
    end = Date.parse(rows[rows.length - 1].day),
    day = 86400000;
  const span = Math.max(day, end - start + day),
    maximum = Math.max(1, ...rows.map((r) => r.count));
  const width = Math.max(1, Math.min(48, ((540 * day) / span) * 0.72));
  return (
    <>
      <svg
        className="analysis-activity"
        viewBox="0 0 600 180"
        role="img"
        aria-label={`날짜별 ${noun} 수. 한국 시간 기준`}
      >
        <line x1="30" y1="145" x2="570" y2="145" stroke="currentColor" opacity=".18" />
        {rows.map((r) => {
          const x = 30 + ((Date.parse(r.day) - start + day / 2) / span) * 540;
          const height = (r.count / maximum) * 112;
          return (
            <g key={r.day}>
              <title>
                {r.day}: {r.count}건
              </title>
              <rect
                x={x - width / 2}
                y={145 - height}
                width={width}
                height={height}
                rx={Math.min(4, width / 2)}
                fill="currentColor"
              />
              {rows.length <= 10 && (
                <text x={x} y={138 - height} textAnchor="middle">
                  {r.count}
                </text>
              )}
            </g>
          );
        })}
        <text x="30" y="170">
          {rows[0].day}
        </text>
        <text x="570" y="170" textAnchor="end">
          {rows[rows.length - 1].day}
        </text>
      </svg>
      <details className="analysis-data-table">
        <summary>날짜별 집계 보기</summary>
        <dl>
          {rows.map((r) => (
            <div key={r.day}>
              <dt>{r.day}</dt>
              <dd>{r.count.toLocaleString()}건</dd>
            </div>
          ))}
        </dl>
      </details>
    </>
  );
}

export function GameAnalysisPanel({ endpoint }: { endpoint: string }) {
  const [data, setData] = useState<GameAnalysis | null>(null),
    [error, setError] = useState('');
  const [summary, setSummary] = useState<GameSummary | null>(null),
    [summaryError, setSummaryError] = useState('');
  const [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0);
  const summaryAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    summaryAbort.current?.abort();
    setData(null);
    setError('');
    setSummary(null);
    setSummaryError('');
    setBusy(false);
    void loadGameAnalysis(endpoint, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setData(value);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(errorMessage(e));
      });
    return () => {
      abort.abort();
      summaryAbort.current?.abort();
    };
  }, [endpoint, revision]);
  async function summarize() {
    if (!data || busy) return;
    const abort = new AbortController();
    summaryAbort.current = abort;
    setBusy(true);
    setSummaryError('');
    try {
      const value = await generateGameSummary(endpoint, data.snapshotHash, abort.signal);
      if (!abort.signal.aborted) setSummary(value);
    } catch (e) {
      if (!abort.signal.aborted) setSummaryError(errorMessage(e));
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }
  if (error)
    return (
      <section className="contest-panel">
        <p role="alert">{error}</p>
        <button className="outline-button" onClick={() => setRevision((v) => v + 1)}>
          분석 다시 불러오기
        </button>
      </section>
    );
  if (!data) return <p role="status">게임 통계를 불러오는 중입니다.</p>;
  const f = data.facts,
    disaster = f.mode === 'DISASTER',
    noun = disaster ? '제출' : '설치';
  const facilityRows = f.facilities.map((r) => ({
    ...r,
    label: facilities[r.key as FacilityType]?.name ?? r.label,
  }));
  return (
    <section className="game-analysis" aria-label="게임 분석">
      <section
        className="analysis-summary"
        aria-labelledby="analysis-summary-title"
        aria-busy={busy}
      >
        <div className="analysis-heading">
          <div>
            <span className="analysis-eyebrow">
              <Sparkles size={15} /> AI 요약
            </span>
            <h2 id="analysis-summary-title">기록으로 살펴보는 게임 현황</h2>
          </div>
          <button
            className="solid-button"
            disabled={busy || !data.summaryAvailable || f.records === 0}
            onClick={() => void summarize()}
          >
            {busy ? '분석 중…' : summary ? '저장된 요약 다시 보기' : 'AI 요약 생성'}
          </button>
        </div>
        {summary ? (
          <>
            <p className="analysis-overview">{summary.overview}</p>
            <ul className="analysis-findings">
              {summary.findings.map((item, i) => (
                <li key={i}>
                  <span>{evidenceNames[item.evidence]}</span>
                  <p>{item.text}</p>
                </li>
              ))}
            </ul>
            <ul className="analysis-cautions">
              {summary.cautions.map((text, i) => (
                <li key={i}>{text}</li>
              ))}
            </ul>
            <small>
              Upstage {summary.model} ·{' '}
              {new Date(summary.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}{' '}
              생성 · AI 설명은 원 통계와 함께 확인하세요.
            </small>
          </>
        ) : (
          <p>
            {!data.summaryAvailable
              ? 'AI 요약 연결을 준비하고 있습니다. 아래 통계는 바로 확인할 수 있습니다.'
              : f.records === 0
                ? '플레이 기록이 쌓이면 요약을 생성할 수 있습니다.'
                : '참여·설치·제출·점수 분포를 바탕으로 현황과 해석할 때의 주의점을 정리합니다.'}
          </p>
        )}
        {summaryError && (
          <p role="alert" className="contest-error">
            {summaryError}{' '}
            <button className="analysis-reload" onClick={() => setRevision((v) => v + 1)}>
              최신 통계 불러오기
            </button>
          </p>
        )}
      </section>
      <div className="analysis-heading">
        <h2>
          <ChartNoAxesCombined size={21} /> 게임 통계
        </h2>
        <span className="contest-badge">{statusNames[f.status] ?? f.status}</span>
      </div>
      <dl className="analysis-totals">
        {[
          ['참여 플레이어', f.participants, '명'],
          [`전체 ${noun}`, f.records, '건'],
          ['점수 기록 있음', f.scoredRecords, '건'],
          ['점수 대기·보류', f.records - f.scoredRecords, '건'],
        ].map(([label, value, unit]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {Number(value).toLocaleString()}
              <small>{unit}</small>
            </dd>
          </div>
        ))}
      </dl>
      <div className="analysis-grid">
        <section className="analysis-chart">
          <h3>시설별 구성</h3>
          <Bars rows={facilityRows} label="시설별 수와 면적" />
        </section>
        <section className="analysis-chart">
          <h3>구별 설치 분포</h3>
          <Bars rows={f.districts} label="구별 시설 수와 면적" />
        </section>
        <section className="analysis-chart">
          <h3>일별 {noun} 추이</h3>
          <ActivityChart rows={f.activity} noun={noun} />
        </section>
        <section className="analysis-chart">
          <h3>평가 그룹별 점수 분포</h3>
          {f.scoreGroups.length ? (
            f.scoreGroups.map((g, i) => (
              <div className="analysis-score-group" key={g.key}>
                <h4>
                  평가 그룹 {i + 1} <small>{g.count.toLocaleString()}명</small>
                </h4>
                <div
                  className="analysis-score-stack"
                  role="img"
                  aria-label={`음수 ${g.negative}명, 0 ${g.zero}명, 양수 ${g.positive}명`}
                >
                  {[
                    ['negative', g.negative],
                    ['zero', g.zero],
                    ['positive', g.positive],
                  ].map(
                    ([kind, n]) =>
                      Number(n) > 0 && (
                        <i key={kind} className={String(kind)} style={{ flex: Number(n) }} />
                      )
                  )}
                </div>
                <p className="analysis-score-labels">
                  <span>음수 {g.negative}</span>
                  <span>0 {g.zero}</span>
                  <span>양수 {g.positive}</span>
                </p>
                <p className="analysis-score-range">
                  최소 {physicalAmount(g.minimumM3)} · 최대 {physicalAmount(g.maximumM3)} m³
                </p>
              </div>
            ))
          ) : (
            <p className="analysis-empty">비교 가능한 점수 기록이 없습니다.</p>
          )}
        </section>
      </div>
      <p className="analysis-note">
        {disaster
          ? '시설은 모든 제출 설계의 합계로, 재제출을 포함합니다. 점수 분포는 같은 평가 조건의 개인 최고 기록입니다.'
          : '점수 기록이 있어도 최신 관측까지 계산이 끝났다는 뜻은 아닙니다. 점수 분포는 같은 평가 조건의 개인 합계입니다.'}{' '}
        {new Date(data.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} 기준
      </p>
    </section>
  );
}
