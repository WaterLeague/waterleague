import { Download, LockKeyhole, ArrowRight, ShieldCheck } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { Placement, Lab } from '../../game/entity/game';
import { useResearch } from '../controller/useResearch';
import { CostPerformance, MetricsComparison } from './ResearchComparison';
import { format, facilities } from '../../game/service/gameService';
import { Hydrograph } from '../../game/view/Hydrograph';
export function ResearchPage({
  account,
  lab,
  onReplay,
}: {
  account: Account | null;
  lab: Lab;
  onReplay: (p: Placement[]) => void;
}) {
  const { consents, entries, detail, error, revision, setRevision, inspect, consent } = useResearch(
    account,
    lab.modelHash
  );
  return (
    <section className="full-page">
      <div className="page-eyebrow">
        RESEARCH WORKSPACE <span>TRACEABLE BY DESIGN</span>
      </div>
      <h1>점수 뒤에 있는 선택들.</h1>
      <p className="lead">
        시설 배치와 변경 과정, 가정과 원본 입력까지. 다시 실행할 수 있는 기록을 남깁니다.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {account?.role === 'ADMIN' ? (
        <div className="empty-state">
          <ShieldCheck size={34} />
          <h3>관리자는 회원 승인을 담당합니다.</h3>
          <p>연구 자료는 동의된 조직 회원만 열람할 수 있습니다.</p>
        </div>
      ) : !account ? (
        <div className="empty-state">
          <LockKeyhole size={34} />
          <h3>로그인 후 연구 공유 설정</h3>
          <p>플레이어는 공유할 기관을 선택하고, 승인된 기관은 동의된 기록을 분석합니다.</p>
        </div>
      ) : account.memberType === 'PLAYER' ? (
        <>
          <div className="scope-note">
            <ShieldCheck />
            <p>
              동의한 기관에는 제출한 전략과 그 버전까지의 변경 이력·계산 결과를 제공합니다. 철회하면
              이후 열람과 다운로드가 즉시 차단됩니다. 이미 내려받은 파일은 자동 회수되지 않습니다.
            </p>
          </div>
          <h2>내 기록을 공유할 기관</h2>
          {consents.length ? (
            consents.map((c) => (
              <label className="consent-row" key={c.organizationId}>
                <span>
                  <b>{c.name}</b>
                  <small>제출 전략 · 배치 이력 · 계산 입력과 결과</small>
                </span>
                <input
                  type="checkbox"
                  checked={c.granted}
                  onChange={(e) => void consent(c.organizationId, e.target.checked)}
                />
              </label>
            ))
          ) : (
            <div className="empty-state">
              <p>아직 승인된 연구기관이 없습니다.</p>
              <small>기관 등록 전에는 누구에게도 상세 플레이 기록이 공유되지 않습니다.</small>
            </div>
          )}
        </>
      ) : (
        <>
          <CostPerformance entries={entries} onSelect={(id) => void inspect(id)} />
          <div className="research-layout">
            <div>
              <h2>
                동의된 제출 기록 <small>{entries.length}</small>
              </h2>
              {entries.map((e) => (
                <button
                  className="research-row"
                  key={e.jobId}
                  onClick={() => void inspect(e.jobId)}
                >
                  <div>
                    <b>{format.format(e.score)} 점</b>
                    <span>
                      버전 {e.revision} · {new Date(e.submittedAt).toLocaleDateString('ko-KR')}
                    </span>
                    <p>{e.designNote || '설계 메모 없음'}</p>
                  </div>
                  <ArrowRight size={17} />
                </button>
              ))}
              {!entries.length && (
                <p className="empty-state">이 기관에 동의한 제출 기록이 없습니다.</p>
              )}
            </div>
            <div>
              {detail ? (
                <>
                  <div className="scope-note">
                    <b>EXPLORATORY</b>
                    <span>현장 검증 전 · 실제 효과 추정 불가</span>
                  </div>
                  {!!detail.leagueContexts?.length && (
                    <details className="research-league-context">
                      <summary>이 계산을 제출한 리그 {detail.leagueContexts.length}개</summary>
                      {detail.leagueContexts.map((l) => (
                        <div key={l.id}>
                          <b>{l.title}</b>
                          <p>
                            {l.state === 'CANCELLED'
                              ? '취소된 리그 · ' + l.cancellationReason
                              : '고정 조건 제출 기록'}
                          </p>
                          <code className="hash-value">규칙 SHA-256: {l.rulesHash}</code>
                        </div>
                      ))}
                    </details>
                  )}
                  <Hydrograph job={detail.simulation} rainfall={detail.lab.model.rainfall} />
                  <MetricsComparison detail={detail} />
                  <h3>서버에 저장된 변경 이력</h3>
                  <label className="revision-selector">
                    버전 {detail.history[revision]?.revision}
                    <input
                      aria-label="설계 이력 버전"
                      type="range"
                      min="0"
                      max={detail.history.length - 1}
                      value={revision}
                      onChange={(e) => setRevision(Number(e.target.value))}
                    />
                  </label>
                  <div className="placement-table">
                    {detail.history[revision]?.placements.map((p) => (
                      <p key={p.cellId}>
                        <b>
                          {p.cellId} · {facilities[p.facilityType].name}
                        </b>
                        <span>{p.areaM2} m²</span>
                      </p>
                    ))}
                  </div>
                  <button
                    className="outline-button"
                    disabled={detail.lab.modelHash !== lab.modelHash}
                    onClick={() => onReplay(detail.history[revision].placements)}
                  >
                    이 배치를 3D에서 확인 <ArrowRight size={15} />
                  </button>
                  <a
                    className="primary-button"
                    href={`/api/v1/research/strategies/${detail.simulation.id}/bundle`}
                  >
                    재현 묶음 다운로드 <Download size={16} />
                  </a>
                  <p className="micro-note">
                    INP·RPT·OUT·시계열·모델·빌더·해시·변경 이력 포함. 다운로드 시 기관 소속과 동의
                    재확인.
                  </p>
                </>
              ) : (
                <div className="empty-state">기록을 선택하면 상세 분석이 열립니다.</div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
