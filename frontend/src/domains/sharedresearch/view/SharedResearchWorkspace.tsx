import { useState } from 'react';
import { Download, ArrowRight, RefreshCw } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import { isOrganizationMember } from '../../account/entity/account';
import { facilities, won } from '../../game/service/gameService';
import { currentWeek, useSharedResearch } from '../controller/useSharedResearch';
import { recordsPath } from '../repository/sharedResearchRepository';
import type { SharedDetail } from '../dto/sharedResearchDto';
import './shared-research.css';
const amount = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 4 });
const at = (time: string) =>
  new Date(time).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
function FlowChart({ detail: d }: { detail: SharedDetail }) {
  const frames = d.frames,
    max = Math.max(1e-9, ...frames.flatMap((f) => [f.baseline.runoffM3s, f.strategy.runoffM3s]));
  const first = Date.parse(frames[0].strategy.at),
    last = Date.parse(frames[frames.length - 1].strategy.at);
  const path = (key: 'baseline' | 'strategy') =>
    frames
      .map(
        (f, i) =>
          `${i ? 'L' : 'M'}${20 + (660 * (Date.parse(f.strategy.at) - first)) / Math.max(1, last - first)},${170 - (145 * f[key].runoffM3s) / max}`
      )
      .join(' ');
  return (
    <figure className="shared-record-chart">
      <figcaption>
        표면 유출 유량 <span>시설 없음 / 설치 조건 · m³/s</span>
      </figcaption>
      <svg
        viewBox="0 0 700 200"
        role="img"
        aria-label={`시설 설치 전후 표면 유출 유량 비교. 전체 ${d.sampleCount}분 중 ${frames.length}시점 표시`}
      >
        <path d="M20 20 V170 H680" className="record-chart-axis" />
        <path d={path('baseline')} className="record-chart-base" />
        <path d={path('strategy')} className="record-chart-design" />
        <text x="22" y="18">
          {amount.format(max)}
        </text>
        <text x="20" y="192">
          {at(frames[0].strategy.at)}
        </text>
        <text x="680" y="192" textAnchor="end">
          {at(frames[frames.length - 1].strategy.at)}
        </text>
      </svg>
      <p>
        회색: 시설 없음 · 녹색: 설치 조건. {d.frameStride}분 간격의 실제 계산값 표시이며, 전체 분별
        자료는 재현 파일에 포함됩니다. 도표는 주간 기여가 아닌 설치 이후 누적 계산 구간입니다.
      </p>
    </figure>
  );
}
export function SharedRecordDetail({
  detail: d,
  institution,
}: {
  detail: SharedDetail;
  institution: boolean;
}) {
  const i = d.installation,
    base = d.baselineFinal,
    design = d.strategyFinal;
  const rows: [string, number, number][] = [
    ['초기 수분·저류', base.initialStorageM3, design.initialStorageM3],
    ['강우', base.precipitationM3, design.precipitationM3],
    ['침투', base.infiltrationM3, design.infiltrationM3],
    ['증발', base.evaporationM3, design.evaporationM3],
    ['표면 유출', base.surfaceRunoffM3, design.surfaceRunoffM3],
    ['시설 배수', base.lidDrainageM3, design.lidDrainageM3],
    ['최종 수분·저류', base.storageM3, design.storageM3],
    [
      '순저류 변화',
      base.storageM3 - base.initialStorageM3,
      design.storageM3 - design.initialStorageM3,
    ],
    ['평가체적', base.accountedDischargeM3, design.accountedDischargeM3],
  ];
  return (
    <article className="shared-record-detail" aria-label="공동 설치 연구 상세">
      <div className="scope-note">
        <b>EXPLORATORY</b>
        <span>공개 관측 기반 · 현장 보정 전</span>
      </div>
      <h3>
        {i.playerName} · {facilities[i.facilityType].name}
      </h3>
      <p>
        {i.areaM2.toLocaleString('ko-KR')}㎡ · {won(i.costKrw)} · {i.cellId}
      </p>
      <p>
        설치 {at(i.installedAt)}
        {i.removedAt ? ` · 철거 ${at(i.removedAt)}` : ' · 설치 유지'}
      </p>
      <p>
        {d.summary.stationName} 관측 · {at(d.summary.simulationStart)} —{' '}
        {at(d.summary.simulatedThrough)} KST
      </p>
      <FlowChart detail={d} />
      <table>
        <caption>물수지 · m³</caption>
        <thead>
          <tr>
            <th>항목</th>
            <th>시설 없음</th>
            <th>설치 조건</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, a, b]) => (
            <tr key={label}>
              <th>{label}</th>
              <td>{amount.format(a)}</td>
              <td>{amount.format(b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        유출 물수지 오차 {amount.format(d.summary.runoffContinuityPercent)}%. 순저류를 포함한
        평가체적을 비교하며 실제 침수 저감량으로 해석하지 않습니다.
      </p>
      <details>
        <summary>공개 관측·계산 조건·미확인 가정</summary>
        {[...d.model.assumptions, ...d.evaporation.assumptions].map((a, n) => (
          <p key={n}>{a}</p>
        ))}
        <p>증발산 방식: {d.evaporation.method}</p>
        <p>
          원본 관측 보관:{' '}
          {d.sourceArchive?.complete
            ? '이 계산의 전체 입력 원문 포함'
            : '일부 과거 원문 미포함 · 계산에 사용한 분량은 보존'}
        </p>
      </details>
      <details>
        <summary>시설·토양·유입·단가·예산 입력</summary>
        <pre>{JSON.stringify(d.model, null, 2)}</pre>
      </details>
      <details>
        <summary>분별 계산값 표 · 표시 시점 {d.frames.length}개</summary>
        <div className="shared-record-samples">
          <table>
            <thead>
              <tr>
                <th>시각 KST</th>
                <th>누적 기여 m³</th>
                <th>수심 mm</th>
                <th>토양수분 %</th>
              </tr>
            </thead>
            <tbody>
              {d.frames.map((f) => (
                <tr key={f.strategy.at}>
                  <td>{at(f.strategy.at)}</td>
                  <td>{amount.format(f.contribution.cumulativeM3)}</td>
                  <td>
                    {f.strategy.surfaceDepthMm === null
                      ? '—'
                      : amount.format(f.strategy.surfaceDepthMm)}
                  </td>
                  <td>
                    {f.strategy.soilMoisture === null
                      ? '—'
                      : amount.format(100 * f.strategy.soilMoisture)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <a
        className="primary-button"
        href={'/api/v1' + recordsPath(institution) + '/' + d.jobId + '/bundle'}
      >
        <Download size={16} /> 원본·계산 재현 묶음
      </a>
      <p className="micro-note">
        INP·RPT·OUT·모델·관측 입력·계산 코드·분별 결과 포함. 다운로드 직전 접근 권한과 파일 해시
        재확인.
      </p>
      <code className="hash-value">입력 SHA-256: {d.request.modelSha256}</code>
      <code className="hash-value">강우·기상 SHA-256: {d.request.forcingSha256}</code>
      <code className="hash-value">산출물 목록 SHA-256: {d.manifestSha256}</code>
    </article>
  );
}
export function SharedResearchWorkspace({ account }: { account: Account }) {
  const org = isOrganizationMember(account),
    [institution, setInstitution] = useState(org),
    [week, setWeek] = useState(currentWeek);
  const s = useSharedResearch(account.id, institution, week);
  return (
    <section className="shared-research-workspace" aria-label="서울 공동 모드 연구 기록">
      <header>
        <div>
          <span className="page-eyebrow">SEOUL / PLAY RECORDS</span>
          <h2>공동 지도에 남긴 선택</h2>
          <p>
            {institution
              ? '이 기관에 동의한 회원의 주간 기여순 기록입니다. 전체 참가자 순위와 다릅니다.'
              : '내 설치·철거 이력과 실제 계산에 사용한 입력을 확인합니다.'}
          </p>
        </div>
        <button className="outline-button" onClick={s.refresh} aria-label="공동 기록 새로고침">
          <RefreshCw size={16} />
        </button>
      </header>
      <div className="shared-record-toolbar">
        {org && (
          <div className="segmented">
            <button aria-pressed={institution} onClick={() => setInstitution(true)}>
              동의받은 기록
            </button>
            <button aria-pressed={!institution} onClick={() => setInstitution(false)}>
              내 기록
            </button>
          </div>
        )}
        <label>
          조회 주 시작일{' '}
          <input
            type="date"
            value={week}
            max={currentWeek()}
            onChange={(e) => {
              if (e.target.value) {
                const d = new Date(e.target.value + 'T00:00:00Z');
                d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
                setWeek(d.toISOString().slice(0, 10));
              }
            }}
          />
        </label>
        <button className="text-button" onClick={() => setWeek(currentWeek())}>
          이번 주
        </button>
      </div>
      {s.error && (
        <p className="form-error" role="alert">
          {s.error}
        </p>
      )}
      <div className="shared-record-layout">
        <div>
          <p className="micro-note">한국시간 월요일 시작 · 최대 100곳 · 음수 기여 포함</p>
          {s.loading && <p role="status">공동 기록을 불러오는 중입니다.</p>}
          {s.records?.entries.map((e) => (
            <button
              key={e.installationId}
              className="research-row"
              aria-pressed={s.detail?.jobId === e.jobId}
              disabled={!e.bundleAvailable}
              onClick={() => void s.inspect(e.jobId)}
            >
              <div>
                <b>
                  {e.playerName} · {amount.format(e.playerScoreM3)}m³
                </b>
                <span>
                  {facilities[e.facilityType].name} · {e.areaM2}㎡ · 이 설치{' '}
                  {amount.format(e.scoreM3)}m³
                </span>
                <small>
                  {e.evaluatedMinutes.toLocaleString('ko-KR')}분 계산 · {at(e.evaluatedThrough)}까지
                  {e.removedAt ? ' · 철거됨' : ''}
                </small>
                {!e.bundleAvailable && <small>산출물 해시 고정 이전 기록 · 상세 제공 보류</small>}
              </div>
              <ArrowRight size={17} />
            </button>
          ))}
          {!s.loading && s.records && !s.records.entries.length && (
            <p className="empty-state">
              이 주에 열람 가능한 계산 기록이 없습니다. 설치 이후 유효한 관측으로 계산이 완료되면
              표시됩니다.
            </p>
          )}
        </div>
        {s.detail ? (
          <SharedRecordDetail detail={s.detail} institution={institution} />
        ) : (
          <div className="empty-state">기록을 선택하면 시설의 물 흐름과 계산 근거가 열립니다.</div>
        )}
      </div>
      <details className="research-sharing">
        <summary>내 공동 설치 기록의 기관별 연구 공유</summary>
        <p>
          선택한 기관에 공동 모드의 설치·철거·주간 기여·상세 계산 입력과 산출물을 제공합니다. 기존
          제출 전략 동의와 별개입니다. 철회하면 이후 열람·다운로드가 차단되며 이미 받은 파일은 자동
          회수되지 않습니다. 실제 사업 활용 동의는 포함하지 않습니다.
        </p>
        {s.consents.map((c) => (
          <label className="consent-row" key={c.organizationId}>
            <span>
              <b>{c.name}</b>
              <small>공동 설치 기록 · 연구 목적</small>
            </span>
            <input
              type="checkbox"
              checked={c.granted}
              disabled={s.saving}
              onChange={(e) => void s.consent(c.organizationId, e.target.checked)}
            />
          </label>
        ))}
        {!s.consents.length && (
          <p>승인된 연구기관이 없습니다. 동의 전에는 상세 기록이 공유되지 않습니다.</p>
        )}
      </details>
    </section>
  );
}
