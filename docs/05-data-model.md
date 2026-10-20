# 현재 데이터 모델

기준일: 2026-10-20. 실제 스키마의 기준은 [Flyway 마이그레이션](../backend/src/main/resources/db/migration)과 [Java 마이그레이션](../backend/src/main/java/db/migration)이다. 아래는 구현된 테이블의 책임 요약이며, 초기 기획의 개념 테이블을 실제 테이블처럼 나열하지 않는다. 배포 전 단일 구조 정리는 [확장 목표](09-delivery.md)에 따른다.

UUID, UTC 시각, 비용·면적의 고정 정밀도를 사용한다. FK·CHECK·UNIQUE·트랜잭션으로 불변식을 보호한다. 소유·권한·상태는 관계형 데이터, JSON은 규칙·요청·결과의 스냅샷과 메타데이터에 사용한다.

| 영역 | 실제 테이블 |
| --- | --- |
| 계정·기관·보안 | `accounts`, `organizations`, `account_mfa`, `account_reviews`, `rate_limits`, `audit_events`, `SPRING_SESSION`, `SPRING_SESSION_ATTRIBUTES` |
| 저장 설계·계산 | `strategies`, `strategy_versions`, `simulation_jobs`, `queue_admission`, `submissions` |
| 주간 설치·계산 | `shared_installations`, `shared_physics_jobs`, `shared_weekly_scores`, `budget_ledger_entries`, `shared_research_consents` |
| 재해 설계·실험·제출 | `historical_design_revisions`, `historical_experiments`, `historical_submissions` |
| 기관 리그 | `leagues`, `league_submissions`, `league_participants`, `league_participant_events`, `league_invitations`, `league_teams`, `league_team_members` |
| 연구·목적별 동의 | `research_consents`, `utilization_requests`, `utilization_decisions`, `strategy_reviews` |
| 비교·후보 탐색 | `rainfall_comparisons`, `rainfall_comparison_jobs`, `research_comparisons`, `research_searches`, `research_search_sources`, `research_candidates` |
| 연결 유역·이용조 초안 | `watershed_experiments`, `cistern_map_plans` |

공개 지도·시설·강우·모델·정책은 고정 파일/카탈로그와 매니페스트도 사용한다. 모든 자료 버전을 별도 DB 테이블로 구현했다고 가정하지 않는다. 기관 서버 기능의 존재는 현재 화면 공개 여부와 별개다.

## 입력·해시·결과

실행에 사용한 배치·시설 제원·강우·초기 상태·평가 경계·엔진/코드·수치 정책·비용 출처를 요청/결과와 결속한다. SHA-256 규약에 키/셀 정렬·정밀도·UTF-8·UTC·비유한 값 거부를 포함한다. 닉네임·메모·동의는 물리 입력 해시에서 제외하되 권한·감사는 분리한다. 캐시가 있어도 기간·한도·동의·검증 수준을 재검사한다.

작업은 lease·만료·fencing token·요청 해시를 보존한다. 결과 게시 시 현재 유효한 작업 점유를 다시 검사하고 산출물은 작업/토큰별 비공개 경로에 보관한다. 완료 결과를 새 데이터로 덮어쓰지 않는다. 원자료·분별 상태·요청·manifest의 해시를 확인해 재생한다. 계산 완료와 수치 품질 통과는 별도 상태다.

현재 6종 독립 표면 계산은 `NATIVE_DIRECT_SURFACE_COMPARISON_V1`의 `design-contract.json`과 그 해시를 기존 작업 결과 JSON에 결속한다. 별도 상태 테이블이나 두 번째 점수 원장을 만들지 않는다. EPSG:5186 원형/객체/형상 해시·후보·구 소속, 전체 평가 표면/시설 면적, 제원/참조 조건, UTC 평가 창·초기화·단위·엔진/코드, 실제 모델/배치/기준·설계 INP 해시, 원가 스냅샷/출처·예산 정책을 같은 형식으로 보관한다. 외부 집수면·배수 노드·관망은 미연결 `null`과 `UNCONNECTED_SURFACE_EXPLORATION`으로 남기고 비용 누락은 `NOT_RECORDED`, LCC는 `NOT_CALCULATED`로 구분한다. 주간은 결과의 `designContract`, 재해는 시설별 `designContract`를 사용하며 제출의 구별 결과에도 보존한다. 과거 완료 결과에 새 근거를 소급 생성하지 않는다.

## 예산·설계 revision

`budget_ledger_entries`는 설치·회원, 사업군·시설, 배정/해제, 금액·시각·회계 버전·원 예산 정책을 기록한다. 설치/취소별 중복 기록은 유일 제약으로 막는다. 회원 잠금 뒤 예상 시설/사업 합계를 검사하고 설치와 원장을 함께 저장한다. 취소 허용 여부를 먼저 검사하며 허용된 취소는 최초 배정 금액/정책을 사용한다. 현재 정책은 개인 20억 원이며 별도 사업 재원을 만들어 더하지 않는다.

V30은 소속 구를 같은 이름의 공개 5자리 코드로 이관하고 현재 후보 ID의 길이를 반영한다. 과거 공간 설치는 `source_retired_at`으로 종료 대상으로 분리하며 원 입력·비용·역할을 보존한다. 종료 처리는 원 배정액을 한 번만 해제한다. 재해 설계·실험과 이용조 초안은 `source_dataset`으로 분리한다. 이전 기록은 `PRE_NATIVE_20261020`, 현재는 `SEOUL_NGII_GAME_V2`이며 설계 기본키에 공간 버전을 포함한다. 이전 공간의 대기·실행 작업은 입력을 보존하고 `SPATIAL_SOURCE_RETIRED`로 재시도를 차단한다.

`historical_design_revisions`의 저장 설계와 제출 시 동결한 전체 사건 입력을 구분한다. 최신 revision 충돌과 멱등키의 다른 본문 재사용을 거부한다. `cistern_map_plans`는 `SPATIAL_DRAFT_NOT_INSTALLED` 초안으로, 설치·점유·예산 원장·점수가 아니다.

## 권한·이력

서버 수신·검증 시각을 확정 이력으로 사용하고 클라이언트 시각/마우스 정보와 구분한다. 불필요한 원시 행동 수집은 기본 비활성이다. 기관 조회는 조직·승인·동의 범위를 매번 검사하며 ID만 아는 것으로 접근할 수 없다. 공개 순위는 허용된 닉네임·결과 요약만 반환한다.

연구 비교는 원 소유자의 전략/계산을 참조하고 기관 소유로 복제하거나 자동 동의를 만들지 않는다. 동의 철회 뒤에도 소유자의 기록은 유지하되 기관 조회/다운로드를 차단한다. 패턴의 저장 계보·재계산·후보 생성은 [기관 분석](18-institution-analysis.md), 사업 목적 동의는 [동의 계약](16-utilization-consent.md)에 둔다.

개인정보와 실험 자료를 분리하고 보존·삭제·철회 범위를 관리한다. 참조 무결성을 이유로 개인정보를 무기한 보관하지 않는다. 기존 이관용 컬럼/분기는 현재 구현 사실이며 향후 호환 의무가 아니다.
