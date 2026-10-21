# 현재 데이터 모델

기준일: 2026-10-21. 실제 스키마의 기준은 [Flyway 마이그레이션](../backend/src/main/resources/db/migration)과 [Java 마이그레이션](../backend/src/main/java/db/migration)이다. 아래는 구현된 테이블의 책임 요약이며, 초기 기획의 개념 테이블을 실제 테이블처럼 나열하지 않는다. 배포 전 단일 구조 정리는 [확장 목표](09-delivery.md)에 따른다.

공사비지수 가격 정책은 공간 원본과 별도로 버전을 고정한다. 신규 설치·재해 설계는 현재 허용 가격 버전으로 원가를 생성하고, 기존 원가 원문·해시와 지출은 보존한다. 저장 설계의 새 계산·제출은 원가 해시뿐 아니라 서버 허용 가격 버전의 전체 출처·단가·면적·시설·위치를 대조한다. 서로 다른 가격 버전의 시설을 한 설계에 유지할 수 있으며 시설별 실제 보관 금액을 사업군별로 합산한다. 사용자가 단가나 가격 버전을 선택하는 API는 제공하지 않는다. 지수 환산 원가는 `PUBLIC_REFERENCE_QUANTITY_V2`이며 실제 견적 기준연도는 미확인, 가정 기준연도·목표월·지수·산식은 출처의 `priceAdjustment`에 보관한다.

UUID, UTC 시각, 비용·면적의 고정 정밀도를 사용한다. FK·CHECK·UNIQUE·트랜잭션으로 불변식을 보호한다. 소유·권한·상태는 관계형 데이터, JSON은 규칙·요청·결과의 스냅샷과 메타데이터에 사용한다.

| 영역 | 실제 테이블 |
| --- | --- |
| 계정·기관·보안 | `accounts`, `organizations`, `account_mfa`, `account_reviews`, `rate_limits`, `audit_events`, `SPRING_SESSION`, `SPRING_SESSION_ATTRIBUTES` |
| 저장 설계·계산 | `strategies`, `strategy_versions`, `simulation_jobs`, `queue_admission`, `submissions` |
| 주간 설치·계산 | `shared_installations`, `shared_physics_jobs`, `shared_weekly_scores`, `budget_ledger_entries`, `shared_research_consents` |
| 재해 설계·실험·제출 | `historical_design_revisions`, `historical_experiments`, `historical_submissions` |
| 게임 대회 | `game_competitions`, `game_competition_participants`, `game_competition_submissions`, `game_competition_live_scores` |
| 보존된 연구 리그 | `leagues`, `league_submissions`, `league_participants`, `league_participant_events`, `league_invitations`, `league_teams`, `league_team_members` |
| 연구·목적별 동의 | `research_consents`, `utilization_requests`, `utilization_decisions`, `strategy_reviews` |
| 비교·후보 탐색 | `rainfall_comparisons`, `rainfall_comparison_jobs`, `research_comparisons`, `research_searches`, `research_search_sources`, `research_candidates` |
| 연결 유역·이용조 초안 | `watershed_experiments`, `cistern_map_plans` |

공개 지도·시설·강우·모델·정책은 고정 파일/카탈로그와 매니페스트도 사용한다. 모든 자료 버전을 별도 DB 테이블로 구현했다고 가정하지 않는다. 기관 서버 기능의 존재는 현재 화면 공개 여부와 별개다.

## 입력·해시·결과

실행에 사용한 배치·시설 제원·강우·초기 상태·평가 경계·엔진/코드·수치 정책·비용 출처를 요청/결과와 결속한다. SHA-256 규약에 키/셀 정렬·정밀도·UTF-8·UTC·비유한 값 거부를 포함한다. 닉네임·메모·동의는 물리 입력 해시에서 제외하되 권한·감사는 분리한다. 캐시가 있어도 기간·한도·동의·검증 수준을 재검사한다.

새 Java 스냅샷은 공통 JSON writer에서 Map과 JsonNode의 객체 키를 정렬한다. 비교 불가능한 Map 키는 임의 순서로 직렬화하지 않고 거부한다. 배열 순서·금액 정밀도·null은 보존하며 공유 mapper의 읽기 설정은 변경하지 않는다. 원문 해시는 저장한 바이트를 기준으로 검증하므로 기존 원가/요청/결과를 새 순서로 재작성하거나 해시를 교체하지 않는다.

작업은 lease·만료·fencing token·요청 해시를 보존한다. 결과 게시 시 현재 유효한 작업 점유를 다시 검사하고 산출물은 작업/토큰별 비공개 경로에 보관한다. 완료 결과를 새 데이터로 덮어쓰지 않는다. 원자료·분별 상태·요청·manifest의 해시를 확인해 재생한다. 계산 완료와 수치 품질 통과는 별도 상태다.

현재 일반 시설의 독립 표면 계산은 `NATIVE_DIRECT_SURFACE_COMPARISON_V1`의 `design-contract.json`과 그 해시를 기존 작업 결과 JSON에 결속한다. 설계 근거 자체를 위한 별도 상태 테이블이나 점수 원장을 만들지 않는다. EPSG:5186 원형/객체/형상 해시·후보·구 소속, 전체 평가 표면/시설 면적, 제원/참조 조건, UTC 평가 창·초기화·단위·엔진/코드, 실제 모델/배치/기준·설계 INP 해시, 원가 스냅샷/출처·예산 정책을 같은 형식으로 보관한다. 외부 집수면·배수 노드·관망은 미연결 `null`과 `UNCONNECTED_SURFACE_EXPLORATION`으로 남기고 비용 누락은 `NOT_RECORDED`로 구분한다. 새 계산은 생애비용의 `UNAVAILABLE`/`PARTIAL`/`COMPLETE` 상태와 원장·결과·정책 해시를 `cost.lifeCycleCost`에 결속하며 미확정 총액은 null로 유지한다. 이전 계산의 `NOT_CALCULATED` 상태는 소급 생성하지 않는다. 주간은 결과의 `designContract`, 재해는 시설별 `designContract`를 사용하며 제출의 구별 결과에도 보존한다. 과거 완료 결과에 새 근거를 소급 생성하지 않는다.

후보 응답의 `suitability`는 `SITE_SUITABILITY_V1` 정책 해시·종합 상태·탐색 배치 허용·시공 승인 false와 조건별 판정/사유/공개 근거를 보관한다. 원 후보의 `siteConditions`에 없는 조건은 미확인으로 반환한다. 새 직접 강우 결과는 같은 표를 `designContract.suitability`에 고정하며 정책 원문·판정 코드도 재현 manifest에 포함한다. 금지·미충족 조건부는 설치 API, 저장 설계·실험·제출과 워커 입력/결과 보관에서 차단한다.

연결 근거의 `PUBLIC_SOURCE_FLOW_GRAPH_V1`은 공간 원 객체/집수면·시설·원 모형 절점/관로·출구와 평가 지점을 노드/간선·출처 해시로 결속한다. 면적 배분은 출처별 가용 면적과 고유 배분 식별자의 원장으로 검사하며 물리 계산값을 새로 만들지 않는다. 집수면의 강우·토양·피복·초기 조건은 해당 모델/원문 행에 연결한다. 현재 Native 독립 표면은 시설 직접 강우와 잔여 표면을 구분하고, 공개 연구 관망은 원 INP 연결과 선언 면적의 모형상 배분을 보존한다. 연구 좌표계·수직 기준·실제 지붕 대응·지표 격자가 미확인인 항목은 미연결 상태로 남기며 원형 지도와 임의 접합하지 않는다. 그래프 원문/해시·코드는 기존 작업 산출물과 결과 JSON에 보관한다.

원 지표 비교는 기존 결과 JSON의 `metricComparison`에 단위·평가 경계/창·기준/설계 원값·절대 개선량·보조 비율·미산정/보류 사유를 보관한다. 독립 표면은 `runoffComparison` v2/v3 내부, 공개 관망은 결과 v2 내부에 필수로 두고 구현 원문 `raw_metrics.py`를 같은 manifest에 결속한다. 관망 미연결·지표 격자 미연결·과거 미수집 지속시간·수요 미확보를 0으로 채우지 않는다. 새 공개 관망의 `evaluationMetrics.floodingDuration`에는 공통 평가 창의 동시 월류 시간을 중복 없이 누적하고 원 지표 비교에 결속한다. 지점별 시간의 합·최댓값으로 대체하지 않는다. 구형 RB LID의 덮개 강우 누락은 그래프의 미모형화 상태와 효과 보류로 남긴다. 기존 원 물리 입력/계산과 과거 결과를 보존하고 원 지표·평가체적 차이 기준을 유지한다.

독립 표면 v3의 배출 시각은 `cases[].metrics.timing`의 원 1차 모멘트·중심시각과 `detention`의 부호 있는 차이·비교 상태로 보관한다. 단위는 m³·s와 s이며 공통 평가 시작을 원점으로 한다. 기존 `runoff_metrics.py` 원문·해시를 재현 자료에 포함하고 새 DB 원장이나 시간 점수는 만들지 않는다. 주간 공개 조회·회원 재해 시설 결과에서 같은 필드를 읽으며 전체 사건 제출은 시설별 원 산출물에 보존한다. 무유출·음의 성분 유량·구형 미수집을 구별한다.

V31은 기존 `shared_weekly_scores`·`historical_submissions`에 `score_policy_sha256`·`comparison_group_hash` 쌍을 추가한다. 과거 null은 그대로 보존하고 순위 조건을 소급 생성하지 않는다. 주간 요청/결과와 전체 사건 제출 요청/결과의 `scoreContext`는 정책·실행 환경·시간 규칙 또는 동결 제출 규칙을 묶으며 계산 전에 기록한다. `score-policy.json`·`score-context.json`·구현은 기존 산출물 manifest에 포함한다. 제출은 소수 18자리 HALF_EVEN 값을 명시적으로 게시하고 원 계산값을 유지한다. 회원별 최고 제출 선택·공개 상위 100개·공동 순위는 규칙/계산 집단마다 독립 적용한다. 관리자 조회는 전체 집단의 순위를 산정한 뒤 100건씩 페이지를 나누며 주간의 조건 혼합은 합계 원장을 신설하지 않고 조회 단계에서 보류한다.

## 게임 대회 원장 · V33

`game_competitions`는 주최 조직·생성자·요청 UUID·이름/정보·모드/사건·분 단위 UTC 개최 기간·고정 규칙 원문/해시·점수 정책·공개/취소 상태를 보관한다. 생성자/요청 키가 유일하며 공개 후 규칙 수정 API는 제공하지 않는다. 규칙에 구 목록·허용 시설·시상 순위 구간/1인당 원화 상금·안내를 고정한다.

`game_competition_participants`는 대회/회원별 한 행으로 동의 규칙 해시와 참가 시각을 기록한다. `game_competition_submissions`는 본인의 기존 `historical_submissions.job_id`를 참조하고 참가 행에 외래키로 결속한다. 원 제출을 복제하거나 소유권을 이전하지 않는다.

`game_competition_live_scores`는 대회/설치별 체적·평가 초/종료 시각·비교 집단/정책 해시·원 주간 작업 ID를 보관한다. 설치·참가·원 작업을 외래키로 연결하고 기존 주간 점수와 같은 트랜잭션에서 게시한다. 마감 이후 계산이 끝나도 평가 창은 마감에서 끝난다. 대회 결과는 조건별 회원 합계 또는 재해 최고 제출과 공동 순위를 조회하며 미완료·조건 불일치를 확정 점수로 만들지 않는다.

## 예산·설계 revision

`budget_ledger_entries`는 설치·회원, 사업군·시설, 배정/해제, 금액·시각·회계 버전·원 예산 정책을 기록한다. 설치/취소별 중복 기록은 유일 제약으로 막는다. 회원 잠금 뒤 예상 시설/사업 합계를 검사하고 설치와 원장을 함께 저장한다. 취소 허용 여부를 먼저 검사하며 허용된 취소는 최초 배정 금액/정책을 사용한다. 현재 정책은 개인 20억 원이며 별도 사업 재원을 만들어 더하지 않는다.

V30은 소속 구를 같은 이름의 공개 5자리 코드로 이관하고 현재 후보 ID의 길이를 반영한다. 과거 공간 설치는 `source_retired_at`으로 종료 대상으로 분리하며 원 입력·비용·역할을 보존한다. 종료 처리는 원 배정액을 한 번만 해제한다. 재해 설계·실험과 이용조 초안은 `source_dataset`으로 분리한다. 이전 기록은 `PRE_NATIVE_20261020`, 현재는 `SEOUL_NGII_GAME_V2`이며 설계 기본키에 공간 버전을 포함한다. 이전 공간의 대기·실행 작업은 입력을 보존하고 `SPATIAL_SOURCE_RETIRED`로 재시도를 차단한다.

`historical_design_revisions`의 저장 설계와 제출 시 동결한 전체 사건 입력을 구분한다. 최신 revision 충돌과 멱등키의 다른 본문 재사용을 거부한다. `cistern_map_plans`는 `SPATIAL_DRAFT_NOT_INSTALLED` 초안으로, 설치·점유·예산 원장·점수가 아니다.

이용조 초안 v3의 `request.equipment`는 공개 규격 ID·카탈로그 SHA-256·평면 이동/회전을 받는다. 서버의 `facilities/cistern-specifications-v1.json`에서 규격·외형을 조회해 `equipmentSpecification`·`equipmentGeometry`·명목 용량의 근거를 원문/해시에 보관한다. 외곽 전체가 원 지상 후보에 포함되어야 하며 구멍·오목 경계 침범을 거부한다. 직접 내부 단면 설계(v1/v2)의 면적·깊이·벽 두께와 동시 입력할 수 없다. 장비 외형의 체적을 유효 저류량으로 환산하지 않으며 내부 단면·배수/월류·펌프 곡선·사용 수요는 null이다. 공개 조회 `GET /api/v1/facilities/cistern-specifications-v1`은 해시 고정 원문을 반환하며 화면은 저장 규격도 이 원문과 대조한다. 발주 예산은 실거래 공사비·설치 예산으로 쓰지 않고 정상 설치는 계속 보류한다.

결합 연구 입력의 `connectedCisternDesign`과 `initialization`은 보관 관측 선행 경로에서 함께 사용할 수 있다. 원 요청 → `initialized-coupled-input.json`의 원 집수 기상 → `cistern-network.inp` → 선택 공동 LID 실행 입력 순서로 생성하고, 이용조 `coupledBinding.initialization`에 기상 파생 해시·선행/평가 초·초기 수심 적용 시각·상태 연속 정책을 보관한다. `cistern-evaluation-initial/final.json`은 공통 `evaluation-initial/final-state.json`의 관망 상태와 같아야 한다. 현재 원장에 별도 DB 저장·점수·재이용량을 추가하지 않는다.

관망 연구 요청의 `cistern.placement.drainClosed=true`는 `drain=null`과 함께 일반 배출 중지를 명시하며 필수 `overflow`는 유지한다. false 또는 생략 시 일반 배수구가 필요하다. 서버는 중지 설계를 `design.cistern.drain={"mode":"CLOSED_NO_WITHDRAWAL"}`로 고정하고, 워커는 일반 배수 링크 없이 계산한다. 신규 이용조 물수지의 `drainOperation`은 `GRAVITY_ORIFICE` 또는 `CLOSED_NO_WITHDRAWAL`이며 프론트가 원 설계와 대조한다. 배출 중지 설계에 원장 조건이 없거나 자연배수 원장이 연결되면 정상 결과로 표시하지 않는다.


## 권한·이력

서버 수신·검증 시각을 확정 이력으로 사용하고 클라이언트 시각/마우스 정보와 구분한다. 불필요한 원시 행동 수집은 기본 비활성이다. 기관 조회는 조직·승인·동의 범위를 매번 검사하며 ID만 아는 것으로 접근할 수 없다. 공개 순위는 허용된 닉네임·결과 요약만 반환한다.

연구 비교는 원 소유자의 전략/계산을 참조하고 기관 소유로 복제하거나 자동 동의를 만들지 않는다. 동의 철회 뒤에도 소유자의 기록은 유지하되 기관 조회/다운로드를 차단한다. 패턴의 저장 계보·재계산·후보 생성은 [기관 분석](18-institution-analysis.md), 사업 목적 동의는 [동의 계약](16-utilization-consent.md)에 둔다.

개인정보와 실험 자료를 분리하고 보존·삭제·철회 범위를 관리한다. 참조 무결성을 이유로 개인정보를 무기한 보관하지 않는다. 기존 이관용 컬럼/분기는 현재 구현 사실이며 향후 호환 의무가 아니다.

일반 이용조의 `RAINWATER_CISTERN`은 기존 `shared_installations` 및 재해 설계/제출 원장을 사용한다. `area_m2`는 건물 집수 면적이고 용량은 문헌 관계 ×0.01m로 파생한다. 원형 공간 DB는 변경하지 않고 지붕 허용 종류·제원·단가에 해시 고정 `CISTERN_GAME_EXPLORATION_V1` 확장을 적용한다. 지붕과 탱크 표시는 같은 설치 한 건에 속하며 탱크의 표시 좌표를 실측 토지/관망 데이터로 저장하지 않는다. `cistern_map_plans`는 기존 별도 초안의 보관 경로이며 새 일반 설치가 이 테이블을 거치지 않는다.

## 운영 알림 큐 (V34)

`notification_outbox`는 MEMBER_REGISTERED/WEEKLY_INSTALLED/DISASTER_SUBMITTED와 원 활동 UUID의 유일 조합, 최소 사용자 요약 JSON, 생성/다음 발송 시각, 시도 횟수, 임대 토큰, 전달/실패 시각, 비밀값 없는 HTTP 상태만 저장한다. 업무 테이블 AFTER INSERT 트리거가 동일 트랜잭션에서 생성한다. Discord URL·비밀번호·세션·OTP 원문은 저장하지 않는다. 전달된 기록은 7일, 전체는 최대 30일 보관한다. 계산 워커에 조회/변경 권한을 부여하지 않는다.
