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
| GET /organizations | 승인된 기관 목록 |
| GET /consents, PUT /consents/{organizationId} | 본인 기관별 동의 조회·부여·철회 |
| GET /research/strategies | MFA 인증 승인 기관, 동의된 현재 모델 제출 최대 100건 |
| GET /research/strategies/{jobId} | 승인 기관·동의, 제출 버전까지 이력과 계산 당시 모델 |
| GET /research/strategies/{jobId}/bundle | 승인 기관·동의, 재인가 후 재현 ZIP |

모델 검증·배포 권한은 조직 회원의 리그 운영과 분리. 내부 워커 endpoint 외부 노출 금지. 공식 맵 상세·강우 선택은 후속 구현 대상. 관리자 역할은 ADMIN, 모든 일반/조직 회원 역할은 MEMBER. 조직 회원의 연구·리그 권한은 승인 상태·회원 유형·소속·MFA로 검사한다.

## 회원 승인·리그

| API | 권한·역할 |
| --- | --- |
| POST /auth/mfa/enrollment | 승인된 관리자·조직 회원 비밀번호 확인, 미등록 MFA 연결 시작; no-store·5분 등록 세션 |
| POST /auth/mfa/confirm | 등록 세션·CSRF·OTP 확인 후 업무 세션 발급 |
| GET /admin/members?status=PENDING&after=UUID | 단일 ADMIN, 상태 필터·100건 커서 목록 |
| GET/POST /admin/members/{id}/reviews | ADMIN, 검토 이력·승인/반려/정지·상태 경합 확인 |
| GET /leagues, /leagues/{id} | 공개 리그·고정 규칙·모델 원문·리그 순위, 초안은 비공개 |
| GET /leagues/{id}/mine | 본인 리그 제출 기록 |
| POST /leagues/{id}/submissions | 플레이어, jobId·rulesHash 확인·한도·기간·실행 지문 검사 |
| GET/POST /institution/leagues | 승인된 기업·기관·정부 회원, 소속 조직 초안 목록·생성 |
| PUT /institution/leagues/{id} | 동일 소속, 공개 전 초안만 수정·revision 경합 검사 |
| POST /institution/leagues/{id}/publish | 동일 소속, 규칙 해시 확인 후 공개·불변 |
| POST /institution/leagues/{id}/cancel | 동일 소속, 사유 기록·신규 제출 중지 |

가입 입력: username, password, memberType, organizationName, purpose. PLAYER는 조직명·이용 목적 빈 값. 조직 유형은 둘 다 필수. 승인 입력: decision(APPROVE/REJECT/SUSPEND), expectedStatus, reason, 선택 organizationId. role·승인 상태·조직 ID를 가입 입력으로 받지 않는다.

리그 참가만으로 연구 동의를 부여하지 않는다. 조직 리그 결과는 주최 조직에 대한 별도 동의가 있는 경우에만 연구 열람·내보내기에 포함한다.

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
