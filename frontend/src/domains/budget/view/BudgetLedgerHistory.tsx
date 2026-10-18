import { useEffect, useState } from 'react';
import type { Budget, BudgetLedger } from '../dto/budgetDto';
import { loadBudgetLedger } from '../repository/budgetRepository';
import { facilities, won } from '../../game/service/gameService';

export function BudgetLedgerHistory({ budget }: { budget: Budget }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<BudgetLedger | null>(null);
  const [cursor, setCursor] = useState<string>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setCursor(undefined);
    setPage(null);
  }, [budget.allocatedKrw, budget.personal]);
  useEffect(() => {
    setPage(null);
    if (!open || !budget.personal) return;
    const abort = new AbortController();
    setBusy(true);
    setError('');
    loadBudgetLedger(cursor, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setPage(value);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError('설치·예산 반환 기록을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [open, cursor, budget.allocatedKrw, budget.personal]);
  return (
    <details
      className="budget-evidence budget-ledger"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>내 설치·예산 반환 기록</summary>
      <p>시즌 종료·이전 설계 취소에 따른 배정액 반환 · 실제 공사비 환급 아님</p>
      {busy && <p role="status">기록 조회 중</p>}
      {error && <p role="alert">{error}</p>}
      {page && page.entries.length === 0 && <p>설치·예산 반환 기록이 없습니다.</p>}
      {page && (
        <ol>
          {page.entries.map((e) => (
            <li key={e.id}>
              <div>
                <strong>
                  {facilities[e.facilityType].name} ·{' '}
                  {e.eventType === 'ALLOCATE' ? '설치 배정' : '예산 반환'}
                </strong>
                <time dateTime={e.effectiveAt}>
                  {new Date(e.effectiveAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
                </time>
              </div>
              <span>
                {e.eventType === 'ALLOCATE' ? '−' : '+'}
                {won(e.amountKrw)}
              </span>
              {e.provenance === 'LEGACY_IMPORT' && <small>이전 설치 기록에서 이관</small>}
            </li>
          ))}
        </ol>
      )}
      {page?.nextBeforeId && (
        <button type="button" disabled={busy} onClick={() => setCursor(page.nextBeforeId!)}>
          이전 50건
        </button>
      )}
      {cursor && (
        <button type="button" disabled={busy} onClick={() => setCursor(undefined)}>
          최근 기록
        </button>
      )}
    </details>
  );
}
