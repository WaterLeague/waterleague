# API·오류 계약

공통 경로 `/api/v1`, 동일 출처 JSON, 서버 세션. 상태 변경 CSRF 필수. UTC ISO 8601·필드별 SI 단위. 금액 KRW 정수 원. 아래는 2026-10-16 구현된 탐색 모델 계약.

| API | 권한·역할 |
| --- | --- |
| GET /auth/csrf | 공개, CSRF 발급 |
| POST /auth/register, /auth/login | 공개+CSRF, PLAYER 가입·세션 회전 |
| POST /auth/logout, GET /auth/me | 인증, 세션 폐기·본인 요약 |
| GET /catalog, /maps | 공개 자료 목록·승인된 공식 맵 목록 |
| GET /lab | 탐색 모델·셀·분강우·단가 근거·모델 해시 |
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

모델 승인 권한은 기관 관리자와 분리. 내부 워커 endpoint 외부 노출 금지. 공식 맵 상세·강우 선택·기관별 리그 개설/참가/공개 API는 후속 구현 대상이며 현재 제공 경로로 안내하지 않음.

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
