ALTER TABLE shared_installations ADD COLUMN cost_snapshot TEXT;
ALTER TABLE shared_installations ADD COLUMN cost_snapshot_sha256 VARCHAR(64);
ALTER TABLE shared_installations ADD CONSTRAINT installation_cost_snapshot_pair CHECK (
  (cost_snapshot IS NULL AND cost_snapshot_sha256 IS NULL)
  OR (cost_snapshot IS NOT NULL AND cost_snapshot_sha256 IS NOT NULL)
);
COMMENT ON COLUMN shared_installations.cost_snapshot IS '설치 당시 수량·공개 참고 단가·미산정 범위; 이전 기록 소급 적용 없음';
