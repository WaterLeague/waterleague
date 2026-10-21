import { useState } from 'react';
import { ShieldCheck, ArrowRight } from 'lucide-react';
import { useApprovals } from '../controller/useApprovals';
import { approvalNames, decisionNames, decisionsFor } from '../service/approvalService';
import { memberTypeNames } from '../../account/entity/account';
import { SitePageHeader } from '../../../shared/ui/SitePageHeader';
export function ApprovalPage() {
  const a = useApprovals(),
    [decision, setDecision] = useState('APPROVE'),
    [reason, setReason] = useState(''),
    [organization, setOrganization] = useState('');
  return (
    <main className="site-page approval-page">
      <SitePageHeader
        title="회원 관리"
        description="기업·기관·정부 회원의 소속과 이용 목적을 검토하고 결과를 기록합니다."
      />
      <div className="scope-note">
        <ShieldCheck />
        <p>
          관리자는 한 계정입니다. 조직 회원의 승인 권한과 플레이 기록의 연구 열람 권한은 분리되어
          있습니다.
        </p>
      </div>
      <label className="filter-label">
        회원 상태
        <select value={a.status} onChange={(e) => a.setStatus(e.target.value)}>
          {Object.entries(approvalNames).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
          <option value="ALL">전체</option>
        </select>
      </label>
      {a.error && (
        <p role="alert" className="form-error">
          {a.error}
        </p>
      )}
      {a.notice && <p role="status">{a.notice}</p>}
      <div className="approval-layout">
        <div>
          {a.rows.map((m) => (
            <button
              className="research-row"
              key={m.id}
              aria-pressed={a.selected?.id === m.id}
              onClick={() => {
                void a.inspect(m);
                setDecision(decisionsFor(m)[0] ?? '');
                setReason('');
                setOrganization('');
              }}
            >
              <div>
                <b>{m.organizationName || m.displayName}</b>
                <span>
                  {memberTypeNames[m.memberType]} · {m.username} · {approvalNames[m.approvalStatus]}
                </span>
                <p>
                  {m.purpose ||
                    (m.memberType === 'PLAYER' ? '일반 플레이어' : '가입 목적 기록 없음')}
                </p>
              </div>
              <ArrowRight size={17} />
            </button>
          ))}
          {!a.rows.length && (
            <div className="empty-state">
              {a.busy ? '신청 확인 중' : '해당 상태의 회원이 없습니다.'}
            </div>
          )}
          {a.hasMore && (
            <button className="outline-button" disabled={a.busy} onClick={() => void a.more()}>
              다음 회원 보기
            </button>
          )}
        </div>
        <aside className="approval-detail">
          {a.selected ? (
            <>
              <span className="eyebrow">가입 신청</span>
              <h2>{a.selected.organizationName || a.selected.displayName}</h2>
              <dl>
                <div>
                  <dt>회원 유형</dt>
                  <dd>{memberTypeNames[a.selected.memberType]}</dd>
                </div>
                <div>
                  <dt>아이디</dt>
                  <dd>{a.selected.username}</dd>
                </div>
                <div>
                  <dt>신청 시각</dt>
                  <dd>{new Date(a.selected.createdAt).toLocaleString('ko-KR')}</dd>
                </div>
              </dl>
              <p className="application-purpose">{a.selected.purpose || '일반 플레이어 가입'}</p>
              {decisionsFor(a.selected).length > 0 && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void a.decide(decision, reason, decision === 'APPROVE' ? organization : '');
                  }}
                >
                  <label>
                    검토 결과
                    <select value={decision} onChange={(e) => setDecision(e.target.value)}>
                      {decisionsFor(a.selected!).map((d) => (
                        <option key={d} value={d}>
                          {decisionNames[d]}
                        </option>
                      ))}
                    </select>
                  </label>
                  {decision === 'APPROVE' && a.selected.memberType !== 'PLAYER' && (
                    <label>
                      승인할 소속
                      <select
                        value={organization}
                        onChange={(e) => setOrganization(e.target.value)}
                      >
                        <option value="">
                          {a.selected.organizationId
                            ? '기존 승인 소속 유지'
                            : '신청 조직명으로 새 조직 등록'}
                        </option>
                        {a.organizations.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name}
                          </option>
                        ))}
                      </select>
                      <small>
                        동명이면 자동 연결하지 않습니다. 동일 조직 소속을 확인한 경우에만 기존
                        조직을 선택하세요.
                      </small>
                    </label>
                  )}
                  <label>
                    검토 사유
                    <textarea
                      required
                      maxLength={1000}
                      rows={4}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="소속 확인 결과·승인 근거 또는 보완 사항"
                    />
                  </label>
                  <button
                    className="primary-button"
                    disabled={a.busy || !reason.trim()}
                    type="submit"
                  >
                    {decisionNames[decision]} 결과 저장
                  </button>
                </form>
              )}
              <h3>검토 이력</h3>
              {a.reviews.map((r, i) => (
                <div className="approval-review" key={i}>
                  <b>{decisionNames[r.decision]}</b>
                  <time>{new Date(r.reviewedAt).toLocaleString('ko-KR')}</time>
                  <p>{r.reason}</p>
                </div>
              ))}
              {!a.reviews.length && <p className="footnote">아직 검토 이력이 없습니다.</p>}
            </>
          ) : (
            <div className="empty-state">
              <ShieldCheck size={32} />
              <p>검토할 회원을 선택하세요.</p>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
