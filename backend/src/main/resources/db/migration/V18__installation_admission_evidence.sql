ALTER TABLE shared_installations ADD COLUMN admission_snapshot TEXT;
COMMENT ON COLUMN shared_installations.admission_snapshot IS '신규 설치 시 적용한 공개 시설 제외 정책; 이전 설치는 미기록 상태 유지';
