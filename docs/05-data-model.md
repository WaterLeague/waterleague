# 데이터 모델

UUID, UTC timestamptz, 비용·면적 고정 정밀도. FK·CHECK·UNIQUE·트랜잭션으로 불변식 보호. JSON은 불변 스냅샷·메타데이터 용도, 소유·권한·검증 상태는 관계형 컬럼.

아래 표는 초기 개념 모델이며 실제 테이블/컬럼 계약은 `backend/src/main/resources/db/migration/`의 적용 순서와 기능별 문서 참조. 사용자 정정 이후 회원은 `accounts`와 조직 유형/승인 상태로 구현하고, 관리자는 단일 계정. 비용은 KRW.

| 엔티티 | 주요 필드·제약 |
| --- | --- |
| users | id, 정규화 email unique, nickname, password_hash, status |
| organizations | id, name, verification_status |
| organization_members | org_id, user_id, role, status, unique(org,user) |
| data_sources | provider, source_uri, license, acquired_at, source_hash, coverage |
| map_versions | map_id, version, boundary, CRS, source_manifest_hash |
| model_versions | map_version_id, engine/build_hash, model_hash, validation_level, intended_use, status |
| model_assumptions | parameter, value/unit, source_type, evidence, range |
| validation_reports | model_version_id, report_hash, reviewer, metrics, scope, approved/revoked_at |
| placement_cells | geometry, subcatchment_id, surface, max_area_m2, feasibility |
| facility_versions | type, parameter_hash, allowed_surfaces, unit_cost_krw, physical_constraints |
| rainfall_scenarios | source_id, station_id, start/end, interval_seconds, quality_status, data_hash |
| leagues | org_id(nullable general), state, starts/ends_at, published_rules_hash |
| league_rules | model_version, rainfall_hash, initial_state_hash, weights, budget, submission_limit |
| league_participants | league_id, user_id, status, accepted_rules_hash, accepted_at |
| strategies | owner_id, map_version_id, created_at |
| strategy_versions | strategy_id, revision, placement_hash, rules_hash, canonical_json |
| placement_events | strategy_id, sequence, server_received_at, operation, before/after, note |
| strategy_permissions | version_id, scope, org_id, consent_version, granted/revoked_at |
| simulation_runs | version_id, evaluation_hash, status, purpose, lease, attempt, metrics, quality_status |
| run_artifacts | run_id, type, hash, size, storage_key, retention |
| submissions | league_id, user_id, version_id, run_id, accepted_at, eligibility |
| leaderboard_entries | league_id, user_id, best_submission_id, raw_score, unique(league,user) |
| strategy_reviews | version_id, org_id, reviewer_id, state, note |
| research_exports | requester/org, consent_snapshot, manifest_hash, expires/downloaded_at |
| audit_events | actor/org, action, resource, outcome, trace_id, occurred_at |

## 불변 경계

맵·모델·시설·강우·규칙·전략 버전·공식 결과 덮어쓰기 금지. 보정은 새 버전, 편집은 새 revision. 승인 철회는 별도 이벤트와 신규 사용 차단. 기존 평가 조건 보존.

## 해시

규약 버전 포함 SHA-256. 키 정렬·셀 ID 정렬·enum 고정·면적 정밀도 고정·UTF-8·UTC·비유한 수 거부. 저자·닉네임·메모·동의는 물리 해시에서 제외하되 접근 권한·기록은 분리.

`evaluation_hash = hash(schema, model, engine_build, rainfall, initial_state, facility, placements, evaluation_boundary, time_settings, numerical_policy)`.

순위 규칙 hash 별도 저장. 캐시가 있어도 기간·한도·동의·검증 수준 재검사.

## 이력·격리

서버가 수신·검증한 변경·계산·제출은 확정 이력. 클라이언트 시각·마우스 telemetry는 사용자 제공 자료로 구분. 순서·before/after·수신시각 보존, 불필요한 원시 행동 수집 기본 비활성.

기관 조회는 org_id·active membership·permission scope 필수. 공개 랭킹은 닉네임·허용 결과 요약만 반환. 전략 ID만 알면 열람 가능한 구조 금지.

개인정보와 실험 데이터 분리. 탈퇴·동의 철회 처리와 보존기간은 운영 전 확정. 참조 무결성을 이유로 개인정보 무기한 보존 금지.

## V9 기관 분석 연결

`research_comparisons`는 organization_id, requested_by, source_job_id, comparison_id FK와 (organization_id, request_key) 유일성, comparison_id 유일성, request_hash, created_at 보존. 기존 `rainfall_comparisons`/`rainfall_comparison_jobs`와 원래 플레이어의 `strategies`/`strategy_versions`/`simulation_jobs`를 연결. 기관 소유 전략 복사·자동 제출·자동 동의 없음. 원본 동의 철회 후에도 소유자의 개인 기록은 보존하되 기관용 API가 현재 권한을 재검사. 패턴 집계는 현재 동의된 입력으로 매 요청 계산하며 공유 캐시/영속 집계 테이블 없음. [기관 분석 계약](26-institution-analysis.md) 참조.
