# API·오류 계약

공통 경로 `/api/v1`, 동일 출처 JSON, 서버 세션. 상태 변경 CSRF 필수. UTC ISO 8601·필드별 SI 단위. 금액 KRW 정수 원. 아래는 2026-10-16 구현된 탐색 모델 계약.

| API | 권한·역할 |
| --- | --- |
| GET /auth/csrf | 공개, CSRF 발급 |
| POST /auth/register, /auth/login | 공개+CSRF, 유형별 가입·승인 상태·세션 회전 |
| POST /auth/logout, GET /auth/me | 인증, 세션 폐기·본인 요약 |
| GET /catalog, /maps | 공개 자료 목록·승인된 공식 맵 목록 |
| GET /lab | 탐색 모델·셀·분강우·단가 근거·모델 해시 |
| GET /spatial/buildings | 인증, 고정 성수 영역 브이월드 건물 대조; no-store·호출 제한 |
| GET /strategies | 본인 저장 설계 목록 |
| POST /strategies | 인증, 첫 불변 버전 저장 |
| POST /strategies/{id}/versions | 소유자, 불변 배치·이력 저장 |
| GET /strategies/{id} | 소유자, 설계와 버전 이력 |
| POST /simulations | 소유자, 비동기 202·Location |
| GET /simulations, /simulations/{id} | 소유자, 상태·품질·결과 |
| GET /simulations/{id}/bundle | 소유자, 계산 성공 시 재현 ZIP |
| POST /submissions | 소유자, 성공한 현재 모델 계산의 탐색 제출 |
| GET /leaderboard | 현재 모델별 공개 최고기록, 서버 재계산 점수 |
| GET /installations/{id}/physics | 공개 공동 시설의 계산 상태·마지막 성공 요약, no-store |
| GET /facilities/epa-designs-v1 | 해시 고정 공개 시설 제원·문헌 범위·출처, ETag·공개 캐시 |
| GET /organizations | 승인된 기관 목록 |
| GET /consents, PUT /consents/{organizationId} | 본인 기관별 동의 조회·부여·철회 |
| GET /research/strategies | MFA 인증 승인 기관, 동의된 현재 모델 제출 최대 100건 |
| GET /research/strategies/{jobId} | 승인 기관·동의, 제출 버전까지 이력과 계산 당시 모델 |
| GET /research/strategies/{jobId}/bundle | 승인 기관·동의, 재인가 후 재현 ZIP |
| GET/POST /research/comparisons | MFA 승인 조직의 동의된 제출 다강우 재계산 목록·생성, 기관별 멱등키 |
| GET /research/comparisons/{id} | 현재 원본 동의·조직 승인 재검사, 원본과 파생 계산 결과 |
| GET /research/comparisons/{id}/jobs/{jobId}/bundle | 현재 동의·기관 분석 그룹 연결 검사, 목적과 원본 연결 포함 ZIP |
| POST /research/patterns | 동일 모델의 동의 제출 1~50개, 상위 고유 설계 1~20개와 경계 동점의 배치 기술 통계 |

모델 검증·배포 권한은 조직 회원의 리그 운영과 분리. 내부 워커 endpoint 외부 노출 금지. 공식 맵 상세·강우 선택은 후속 구현 대상. 관리자 역할은 ADMIN, 모든 일반/조직 회원 역할은 MEMBER. 조직 회원의 연구·리그 권한은 승인 상태·회원 유형·소속·MFA로 검사한다.

공동 시설 물리 상태는 `WAITING/RUNNING/READY/DELAYED/UNAVAILABLE`. `attemptedAt`과 `simulatedThrough` 구분, 실패 시 이전 성공 결과와 그 시각 유지. 무결과는 `result:null`이며 강우·수분·유출 0 대입 없음. 마지막 계산이 5분을 넘으면 지연 표시, 실행 작업이 240초를 넘으면 보류 표시. 결과는 관측소·계산 구간·EPA 버전·EXPLORATORY·누적 강우 체적/침투/증발/유출·현재 수분/저류·시설 표면 수심·토양수분·물수지 오차·증발/초기상태 가정만 공개. 원문·파일 경로·입력 hash·임대 토큰 미노출. 철거·미등록 시설 404. 분별 재현 입력은 별도 접근 통제 대상이며 이 공개 요약에서 제공하지 않음.

## 회원 승인·리그

| API | 권한·역할 |
| --- | --- |
| POST /auth/mfa/enrollment | 승인된 관리자·조직 회원 비밀번호 확인, 미등록 MFA 연결 시작; no-store·5분 등록 세션 |
| POST /auth/mfa/confirm | 등록 세션·CSRF·OTP 확인 후 업무 세션 발급 |
| GET /admin/members?status=PENDING&after=UUID | 단일 ADMIN, 상태 필터·100건 커서 목록 |
| GET/POST /admin/members/{id}/reviews | ADMIN, 검토 이력·승인/반려/정지·상태 경합 확인 |
| GET /leagues, /leagues/{id} | 공개 목록·권한별 상세·고정 규칙·모델 원문·순위, 초안은 비공개 |
| GET /leagues/{id}/mine | 본인 리그 제출 기록 |
| POST /leagues/{id}/submissions | 플레이어, jobId·rulesHash 확인·한도·기간·실행 지문 검사 |
| GET/POST /institution/leagues | 승인된 기업·기관·정부 회원, 소속 조직 초안 목록·생성 |
| PUT /institution/leagues/{id} | 동일 소속, 공개 전 초안만 수정·revision 경합 검사 |
| POST /institution/leagues/{id}/publish | 동일 소속, 규칙 해시 확인 후 공개·불변 |
| POST /institution/leagues/{id}/cancel | 동일 소속, 사유 기록·신규 제출 중지 |

가입 입력: username, password, memberType, organizationName, purpose. PLAYER는 조직명·이용 목적 빈 값. 조직 유형은 둘 다 필수. 승인 입력: decision(APPROVE/REJECT/SUSPEND), expectedStatus, reason, 선택 organizationId. role·승인 상태·조직 ID를 가입 입력으로 받지 않는다.

리그 참가만으로 연구 동의를 부여하지 않는다. 조직 리그 결과는 주최 조직에 대한 별도 동의가 있는 경우에만 연구 열람·내보내기에 포함한다.

리그 초안 추가 입력: `placementLimit`(배치 구역 수), `areaLimitM2`(합산 면적, 소수 두 자리), `award`(`prizeKrw`, `winnerCount`, `notice`). 새 규칙 버전 2에 포함하며 공개 후 고정. 필드 생략 시 모델 상한·상금 없음 적용, 기존 버전 1 규칙 원문·hash 유지. 제출은 저장 배치의 개수·면적을 서버에서 재검사하며 초과 시 422 `LEAGUE_RULES_MISMATCH`. [제한·상금 계약](20-league-limits-awards.md) 참조.

## 리그 참가·팀전 서버 API

schema 3은 초안에 `participation: {access, admission, entryMode, teamSizeLimit}`를 포함. 값·이전 규칙 호환·개인/팀 한도는 [참가 계약](25-league-participation.md) 참조. 신규 초안 화면은 schema 3 참가 방식을 명시하며 기존 schema 1/2 규칙은 그대로 열람·제출.

| API | 입력·권한 |
| --- | --- |
| GET /leagues/joined | 플레이어, 신청 대기/승인 리그 최근 100개 |
| GET /leagues/participations | 플레이어 본인의 모든 참가 상태 요약 최근 100개. 규칙·모델·다른 회원 정보 제외 |
| POST /leagues/invitations/preview | 플레이어, code 본문; 유효한 초대의 고정 규칙만 반환 |
| GET/POST /leagues/{id}/participation | 플레이어 본인 상태·이벤트·팀·누적 횟수 / rulesHash·선택 code로 참가 |
| POST /leagues/{id}/participation/withdraw | 본인, revision; 참가 철회, 제출 이력·횟수 보존 |
| GET /institution/leagues/{id}/participants?after=UUID | MFA 주최 조직, 100건 items·nextCursor |
| GET /institution/leagues/{id}/participants/{owner}/events | 주최 조직, 해당 참가자의 최근 상태 이력 100건 |
| POST /institution/leagues/{id}/participants/{owner}/decisions | 주최 조직, revision·state(APPROVED/REJECTED)·reason |
| GET/POST/DELETE /institution/leagues/{id}/invitation | 주최 조직, 유효 여부·만료 조회 / 코드 신규 발급·회전 / 폐기 |
| POST /leagues/{id}/teams | 승인 참가자, name; 팀 생성·초대 코드 한 번 반환 |
| POST /leagues/{id}/teams/preview | 승인 참가자, code; 팀 이름·정원·규칙 확인 |
| POST /leagues/{id}/teams/join | 승인 참가자, code·teamId·rulesHash; 팀 정원·기존 소속 검사 |
| POST /leagues/{id}/teams/leave | 첫 제출 전 본인 탈퇴; 팀장은 혼자일 때 해산 |
| POST/DELETE /leagues/{id}/teams/invitation | 첫 제출 전 팀장, 팀 코드 회전 / 폐기 |

코드는 URL-safe 43자·POST 본문 전용, DB 해시 저장, 코드 반환 no-store. 변경·코드 검증은 회원별 시간당 120회 제한과 CSRF 적용. 비공개 리그는 공개 목록 제외; 상세 GET은 주최·대기/승인 참가자만, 대기자는 `boardVisible=false`·빈 순위. 참가 반려/탈퇴 후 본인 `/participation` 이력은 계속 조회 가능하나 비공개 상세는 차단. 일반 연구/사업 ZIP에서도 다른 조직의 비공개 리그 맥락 제외. 본인 ZIP에는 자신의 전체 제출 맥락 유지.

`reviewRequired=true`는 OPEN 리그의 재신청도 주최자 검토가 필요함을 뜻함. 승인 변경과 팀 정원·첫 제출 구성 고정·공유 한도는 서버 트랜잭션에서 처리. 불가능한 참가·팀 변경은 409 `LEAGUE_PARTICIPATION_CONFLICT`. 연구 상세와 ZIP의 `leagueContexts[].teamName`은 제출 팀 이름이며 팀원 개인 자료 열람 권한을 부여하지 않음.

## 사업 활용 동의·기관 검토

계산별 불변 요청, 소유자 승인/거절/철회, 기관 검토 이력, 커서 목록·목적별 재현 ZIP은 [활용 계약](17-utilization-consent.md) 참조. 연구 동의와 사업 활용 검토 동의는 독립 범위이며, 사업용 다운로드는 지정 요청의 승인 상태·계산·기관·소유자 상태를 준비 전후 확인한다. 관리자에게 자료 접근 권한을 부여하지 않는다.

기관 재계산·패턴 통계의 요청/응답·권한·원본 소유권·한도·철회 계약은 [기관 분석 계약](26-institution-analysis.md) 참조. 서로 다른 모델의 패턴 혼합은 `ANALYSIS_INCOMPATIBLE` 422, 원본 미동의·타 조직 그룹은 404. 생성은 202, 동일 키/다른 내용 409, 활성 계산 한도 초과 429. 모든 분석 응답은 no-store.

## 배치 입력

title, modelHash, placements[{cellId, facilityType, areaM2}], designNote, baseRevision. 서버 발급 ID 사용, 비용·점수·역할·원격 URL·INP·파일경로는 입력 불가. 알 수 없는 필드·enum·중복 셀·면적 정밀도 위반 거부. 계산 요청은 versionId와 UUID requestKey.

## 오류

RFC 9457 `application/problem+json`: type, title, status, detail, instance, code, traceId, violations[{field,code}]. 커스텀 DomainException·ErrorCode, 공통 RestControllerAdvice. 보안 필터도 동일 serializer. 프론트는 공통 handler에서 code별 안내·재인증·재시도 분기.

| HTTP | 대표 code |
| --- | --- |
| 400 | REQUEST_INVALID, UNKNOWN_FIELD |
| 401 | AUTHENTICATION_REQUIRED, CREDENTIALS_INVALID |
| 403 | ACCESS_DENIED, CSRF_INVALID |
| 404 | RESOURCE_NOT_FOUND, 비공개 존재 여부 보호 |
| 409 | RULES_CHANGED, IDEMPOTENCY_CONFLICT, SUBMISSION_LIMIT_REACHED |
| 422 | PLACEMENT_INVALID, BUDGET_EXCEEDED, MODEL_NOT_ELIGIBLE, RAIN_QUALITY_FAILED |
| 429 | RATE_LIMITED, SIMULATION_QUOTA_EXCEEDED |
| 503 | SIMULATION_UNAVAILABLE, DATASET_UNAVAILABLE |

스택·SQL·내부경로·원문·토큰 비노출. 리스트 크기·sort 제한·cursor. 계산 멱등키 필수, 같은 키 다른 본문 거부. QUEUED/RUNNING/SUCCEEDED/FAILED/REJECTED/CANCELLED 구분, 새로고침 후 상태 복원.

## 강우 모델 카탈로그

- `GET /api/v1/lab/catalog`: 등록 모델의 해시·이름·강우 요약·예산·검증 등급, 기본 모델 해시
- `GET /api/v1/lab?modelHash=…`: 등록 원문의 선택 모델. 생략하면 기존 기본 모델
- `GET /api/v1/leaderboard?modelHash=…`: 해당 모델의 독립 탐색 순위
- `GET /api/v1/research/strategies?modelHash=…`: 선택 조건의 동의된 연구 기록. 조직 승인·MFA 조건 유지
- 기관 리그 초안 요청 `modelHash` 필수. 공개 후 불변, 카탈로그에 수록된 모든 조건의 신규 실행 지원
- 전략의 기존 ID에 다른 모델 버전 추가 시 409. 다른 강우 비교는 새 전략 생성. 미등록 모델은 404

## 계산 재사용 메타데이터

신규 성공 결과의 `result.execution`은 `schema: 1`, `mode: COMPUTED | REUSED`, 64자 SHA-256 `computationKey` 제공. 이전 결과에는 없을 수 있음. 재사용 여부는 평가 점수·리그 제출 자격·기관 동의를 변경하지 않음. 원본 다른 회원의 식별자·작업 ID는 제공하지 않으며 재현 ZIP도 현재 소유자/버전의 요청·이력으로 구성.

## 재해 모드 API 추가

- `GET /api/v1/disasters`: 공개 재해 3건과 각 사건의 25개 구 강우 모델·시각·관측소·분량 제공.
- `POST /api/v1/historical`: 로그인 회원의 선택 구·등록 재해 모델·공개 후보 1~50곳 검사 후 계산 요청. 요청 키 재사용은 같은 입력에만 허용. 다른 구 연구 허용, 공동 위치 점유 변경 없음.
- `GET /api/v1/historical`, `GET /api/v1/historical/{id}`: 요청자 본인의 비공개 작업 목록·상태·결과.
- `GET /api/v1/historical/{id}/bundle`: 본인 성공 작업의 해시 검증된 재현 묶음. 경로 이탈·심볼릭 링크·파일 변조 차단.

재해 설계 예산은 회원당 20억 원이며 여러 구의 설계 초안을 합산. 서울시 빗물관리시설 전체 사업 규모를 개인에게 적용한 게임 규칙으로 실제 지급액이 아님. 결과는 선택 표면의 기준 대비 유출·배수·순저류 체적 비교. 관망·실제 침수 복원 결과로 확대 해석 금지.

## 공동 주간 순위

`GET /api/v1/weekly`는 이번 주·지난주의 25개 구 합계, 개인 상위 100명, 로그인한 본인의 전체 순위, 주간 종료 시각과 확정 우승 구를 제공. 한국시간 월요일 경계, 동점 공동 순위, 음수 기여 보존. 계산 완료 분 수와 설치 이후 예상 분 수가 다르면 종료 주 `PROVISIONAL`; 빈 주 `EMPTY`, 완료 주 `FINAL`. 실제 자료 없는 가상 순위 금지. 2분 처리 여유를 둔 목표 시각·생성 시각·탐색 등급 표시. 응답의 본인 기록에 계정명·이메일·인증 정보 제외.

## 공동 배치예산·시설 비용

`GET /api/v1/budget`는 `policy`(사업 총액 `limitKrw`·개인 한도 `personalLimitKrw` 각각 20억 원, `allocationScope=MEMBER`, 참고연도·출처·원문 해시·규칙 버전), 본인 활성 설치 비용 `allocatedKrw`, `remainingKrw`, `personal`을 반환. 익명은 사용액 0·한도 미리보기·`personal=false`; 다른 회원의 잔액 제공 없음. 본인 ID는 서버 인증에서 결정. 설치·철거 트랜잭션의 회원 행 잠금으로 동시 초과 지출 차단. 소속 구·공유 위치 점유 규칙 유지. 규칙 `SEOUL_PERSONAL_FULL_2026_V3`를 신규 설치 행 `budget_policy`와 재해 요청에 고정. 이전 구별 8천만 원 규칙은 기존 기록 재현에만 보존. 후보의 시설 단가·포함/제외 범위·출처와 저장 설치 비용은 변경하지 않음.

## 공동 설치 연구 기록

`GET/PUT /consents/shared[/{organizationId}]`는 기존 전략 동의와 독립적인 기관별 공동 설치 연구 동의. `GET /installations/records`와 `/installations/records/{jobId}[/bundle]`는 본인 완료 기록. `GET /research/installations` 및 `/research/installations/{jobId}[/bundle]`는 승인된 조직 회원의 현재 기관에 동의된 기록. 목록은 한국시간 주 시작일의 기여·회원 합계 순으로 최대 100개 설치, 상세는 선택한 완료 job에 고정. 이메일·사용자명·IP·키 미포함. 산출물 manifest의 DB 고정 해시·입력 해시·모델/설치 연결 검증 후 다운로드, 과거 manifest 미고정 작업은 내보내기 보류.

상세는 DB에 고정된 manifest SHA-256과 요청·모델·설치 연결을 검사한 완료 작업만 제공. 설치 이후 누적 수문 상태와 주간 합계를 구분하며 화면은 최대 360개 시점을 추출, 원본 분별 결과는 재현 묶음에 보존. 초기 수분·저류, 최종 저류, 순저류 변화 분리. 원문 강우·기상은 계산 연장 시 이전 구간에서 함께 복사하고 원문 누락 여부를 명시. 조회 가능 주는 한국시간 현재 주 이하의 월요일 시작일. 화면 비활성화·조회 범위 변경 시 상세 제거, 복귀·30초 갱신 시 권한 재확인.

계산 원문은 SHA-256별 불변 원본을 프로젝트에 보관하고 각 계산 디렉터리에 하드 링크로 연결. 링크 미지원 저장소는 검증 후 복사. 외부 심볼릭 링크는 거부하며 원문 변경 시 조회 차단. 내보내기의 주간 원문 증가를 수용하도록 manifest 8MiB·최대 50,000개, 합계 원본 512MiB, 개별 파일 64MiB·ZIP 64MiB 제한 적용. 한도를 넘는 파일은 불완전한 묶음 대신 제공 보류.

신규 후보 v5 응답의 `facilityDesignSet`은 공개 제원 ID·SHA-256, `initializationPolicy`는 7일 선행 계산 정책. 물리 상태 응답과 재해 시설 결과의 `initialization`은 시작 토양수분·저류량, 선행 강우 총량·기간, 원문 해시, 구간 평균 적용 분 수와 한계를 포함. 해당 값은 관측 기반 계산이며 토양수분 실측값으로 표시하지 않음. 기존 버전 기록에는 새 초기 상태를 소급 생성하지 않음.

공동 설치 연구 상세의 `initialization`·`facilityDesign`은 manifest 검증을 통과한 해당 작업의 `result.json`에서 반환. 현재 제원 목록이나 DB 요약으로 대체하지 않으며 보관 근거가 없는 기존 기록은 null 반환. 물리 상태·재해 결과·기관 연구 화면은 같은 제원 표시 컴포넌트로 매개변수별 문헌 범위·설계 가정·원문 해시 표시. 본인·현재 기관별 동의·계정 상태 검증 유지.
