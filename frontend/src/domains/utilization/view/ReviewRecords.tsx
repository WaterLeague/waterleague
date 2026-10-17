import type { StrategyReview } from '../entity/utilization';
import { displayTime, reviewLabels } from '../service/utilizationService';
export function ReviewRecords({ items }: { items: StrategyReview[] }) {
  return (
    <div className="utilization-reviews">
      {items.map((r) => (
        <article key={r.id}>
          <header>
            <b>{reviewLabels[r.state]}</b>
            <time>{displayTime(r.createdAt)}</time>
          </header>
          <small>
            {r.organizationName} · 계산 {r.jobId.slice(0, 8)}
          </small>
          <p>{r.reason}</p>
          <div className="review-limitations">
            <b>확인이 필요한 조건</b>
            <p>{r.limitations}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
