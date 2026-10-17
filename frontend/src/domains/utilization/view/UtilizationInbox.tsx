import { useState } from 'react';
import { Download, ArrowRight } from 'lucide-react';
import { useUtilizationInbox } from '../controller/useUtilizationInbox';
import type { Decision, RequestDetail } from '../entity/utilization';
import { decisionLabels, displayTime, stateLabels } from '../service/utilizationService';
import { ReviewRecords } from './ReviewRecords';

function ConsentDetail({
  detail,
  own,
  busy,
  onDecision,
}: {
  detail: RequestDetail;
  own: boolean;
  busy: boolean;
  onDecision: (decision: Decision) => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const r = detail.request;
  return (
    <article className="utilization-detail">
      <div className="utilization-heading">
        <span className="utilization-state">{stateLabels[r.state]}</span>
        <small>{r.organizationName}</small>
      </div>
      <h3>{r.title}</h3>
      <p className="utilization-purpose">{r.purpose}</p>
      <dl>
        <dt>대상 계산</dt>
        <dd>{r.jobId}</dd>
        <dt>저장 버전</dt>
        <dd>{r.versionId}</dd>
        <dt>요청 시각</dt>
        <dd>{displayTime(r.createdAt)}</dd>
      </dl>
      <div className="utilization-boundary">
        <b>사업 활용 검토를 위한 자료 이용</b>
        <p>
          이 기관에 위 계산의 배치·변경 이력·입력·결과 파일을 제공합니다. 실제 시공이나 안전성 승인,
          권리 양도는 포함하지 않습니다.
        </p>
        <p>
          연구 공유와 별도 동의입니다. 연구 공유를 끄더라도 이 동의는 유지됩니다. 철회하면 이후
          다운로드가 차단되며, 이미 내려받은 파일은 자동 회수되지 않습니다.
        </p>
        <p>현재 결과는 현장 검증 전 탐색 계산입니다.</p>
      </div>
      {own && r.state === 'PENDING' && (
        <div className="utilization-decision">
          <label className="utilization-check">
            <input
              type="checkbox"
              checked={acknowledged}
              disabled={busy}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            기관·대상 계산·활용 목적과 제공 범위를 확인했습니다.
          </label>
          <div className="utilization-actions">
            <button
              className="primary-button"
              disabled={busy || !acknowledged}
              onClick={() => onDecision('GRANT')}
            >
              사업 검토 자료 이용에 동의
            </button>
            <button
              className="outline-button"
              disabled={busy}
              onClick={() => onDecision('DECLINE')}
            >
              요청 거절
            </button>
          </div>
        </div>
      )}
      {own && r.state === 'GRANTED' && (
        <button className="outline-button" disabled={busy} onClick={() => onDecision('REVOKE')}>
          사업 활용 동의 철회
        </button>
      )}
      {!own && r.state === 'GRANTED' && (
        <a
          className="primary-button"
          href={`/api/v1/institution/utilization/requests/${r.id}/bundle`}
        >
          이 목적의 재현 묶음 <Download size={16} />
        </a>
      )}
      <details className="utilization-audit">
        <summary>동의 이력과 내용 식별값</summary>
        <p className="hash-value">
          정책 {r.policyVersion}
          <br />
          내용 SHA-256 {r.termsHash}
        </p>
        {detail.decisions.length ? (
          <ol>
            {detail.decisions.map((d) => (
              <li key={d.revision}>
                {decisionLabels[d.decision]} · {displayTime(d.createdAt)}
              </li>
            ))}
          </ol>
        ) : (
          <p>소유자의 결정 전입니다.</p>
        )}
      </details>
    </article>
  );
}
export function UtilizationInbox({
  accountId,
  institution,
  refresh,
}: {
  accountId: string;
  institution: boolean;
  refresh: number;
}) {
  const u = useUtilizationInbox(accountId, institution, refresh);
  const [tab, setTab] = useState<'received' | 'reviews' | 'sent'>('received');
  const requests = tab === 'sent' ? u.sent : u.received;
  return (
    <section className="utilization-workspace">
      <h2>내 기록의 활용</h2>
      <p>리그 제출은 평가 참여입니다. 연구 공유와 사업 활용 동의는 직접 관리합니다.</p>
      <div className="utilization-tabs" role="group" aria-label="활용 기록 보기">
        <button aria-pressed={tab === 'received'} onClick={() => setTab('received')}>
          받은 활용 요청
        </button>
        <button aria-pressed={tab === 'reviews'} onClick={() => setTab('reviews')}>
          기관 검토 의견
        </button>
        {institution && (
          <button aria-pressed={tab === 'sent'} onClick={() => setTab('sent')}>
            보낸 활용 요청
          </button>
        )}
      </div>
      {u.error && (
        <p className="form-error" role="alert">
          {u.error}
        </p>
      )}
      {tab === 'reviews' ? (
        <>
          <ReviewRecords items={u.reviews.items} />
          {!u.reviews.items.length && (
            <p className="empty-state">아직 내 계산에 남겨진 기관 검토 의견이 없습니다.</p>
          )}
          {u.reviews.nextCursor && (
            <button
              className="outline-button"
              disabled={u.busy}
              onClick={() => void u.more('reviews')}
            >
              이전 검토 더 보기
            </button>
          )}
        </>
      ) : (
        <div className="utilization-grid">
          <div>
            <div className="utilization-request-list">
              {requests.items.map((r) => (
                <button
                  key={r.id}
                  aria-pressed={u.selected?.detail.request.id === r.id}
                  onClick={() => void u.open(r.id, tab === 'received')}
                  disabled={u.busy}
                >
                  <div>
                    <small>
                      {r.organizationName} · {stateLabels[r.state]}
                    </small>
                    <b>{r.title}</b>
                    <time>{displayTime(r.createdAt)}</time>
                  </div>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
            {!requests.items.length && (
              <p className="empty-state">
                {tab === 'sent'
                  ? '연구 기록을 선택해 활용 목적을 작성하면 소유자에게 동의를 요청할 수 있습니다.'
                  : '아직 받은 사업 활용 요청이 없습니다. 별도 동의 전에는 사업 목적의 자료 다운로드가 허용되지 않습니다.'}
              </p>
            )}
            {requests.nextCursor && (
              <button className="outline-button" disabled={u.busy} onClick={() => void u.more(tab)}>
                이전 요청 더 보기
              </button>
            )}
          </div>
          {u.selected && u.selected.own === (tab === 'received') ? (
            <ConsentDetail
              key={u.selected.detail.request.id + ':' + u.selected.detail.request.revision}
              detail={u.selected.detail}
              own={u.selected.own}
              busy={u.busy}
              onDecision={(d) => void u.decide(d)}
            />
          ) : (
            <div className="utilization-placeholder">
              요청을 선택하면 목적과 제공 범위를 확인할 수 있습니다.
            </div>
          )}
        </div>
      )}
    </section>
  );
}
