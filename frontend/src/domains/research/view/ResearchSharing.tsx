import { useState } from 'react';
import type { Consent } from '../entity/research';
export function ResearchSharing({
  consents,
  onChange,
}: {
  consents: Consent[];
  onChange: (id: string, granted: boolean) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  return (
    <section className="research-sharing">
      <h2>기관별 연구 공유</h2>
      <p>
        선택한 기관에 제출 전략과 그 버전까지의 변경 이력·계산 결과를 제공합니다. 기관은 같은 배치를
        다른 기상 조건으로 재계산하고, 배치 패턴 분석·패턴 기반 후보 생성·물리 재평가에 사용할 수
        있습니다. 철회하면 이후 연구 열람·재계산·집계·다운로드가 차단됩니다. 이미 받은 파일은 자동
        회수되지 않습니다.
      </p>
      <p>별도로 승인한 사업 활용 동의는 아래 ‘받은 활용 요청’에서 관리합니다.</p>
      {consents.length ? (
        consents.map((c) => (
          <label className="consent-row" key={c.organizationId}>
            <span>
              <b>{c.name}</b>
              <small>연구 목적 · 기록 열람·조건 비교·배치 패턴 분석·후보 생성 및 물리 재평가</small>
            </span>
            <input
              type="checkbox"
              checked={c.granted}
              disabled={busy !== null}
              onChange={async (e) => {
                setBusy(c.organizationId);
                try {
                  await onChange(c.organizationId, e.target.checked);
                } finally {
                  setBusy(null);
                }
              }}
            />
          </label>
        ))
      ) : (
        <p className="empty-state">
          아직 승인된 연구기관이 없습니다. 기관을 선택하기 전에는 상세 기록이 공유되지 않습니다.
        </p>
      )}
    </section>
  );
}
