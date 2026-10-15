# API·오류 계약

목표 경로 `/api/v1`, 동일 출처 JSON, 서버 세션. 상태 변경 CSRF 필수. UTC ISO 8601·필드별 SI 단위. 아래는 목표 계약, 구현 현황은 별도 기록.

| API | 권한·역할 |
| --- | --- |
| GET /auth/csrf | 공개, CSRF 발급 |
| POST /auth/register, /auth/login | 공개+CSRF, PLAYER 가입·세션 회전 |
| POST /auth/logout, GET /auth/me | 인증, 세션 폐기·본인 요약 |
| GET /maps, /maps/{versionId} | 공개 맵·셀·출처·검증 수준 |
| GET /rainfall-scenarios | 맵별 가용 관측 이벤트 |
| GET /leagues | 공개 리그·고정 규칙 |
| POST /strategies | PLAYER, 초안 |
| POST /strategies/{id}/versions | 소유자, 불변 배치·이력 저장 |
| GET /strategies/{id} | 소유자 또는 동의된 권한 |
| POST /simulations | 소유자, 비동기 202·Location |
| GET /simulations/{id} | 소유자/권한, 상태·품질·결과 |
| POST /leagues/{id}/participations | 규칙·동의 후 참가 |
| POST /leagues/{id}/submissions | 참가자, 공식 제출 |
| GET /leagues/{id}/leaderboard | 검증 최고기록 |
| POST /organizations/{id}/leagues | 승인 소속 관리자, 초안 |
| POST /organizations/{id}/leagues/{leagueId}/publish | 소속·소유, 공개 게이트 |
| GET /organizations/{id}/strategies | 소속·동의, 연구 비교 |
| GET /organizations/{id}/strategies/{versionId} | 소속·동의, 상세 이력 |
| POST /organizations/{id}/research-exports | 소속·연구동의, 재현 묶음 |

모델 승인 권한은 기관 관리자와 분리. 내부 워커 endpoint 외부 노출 금지.

## 배치 입력

mapVersionId, rulesHash, placements[{cellId, facilityType, areaM2}], designNote. 서버 발급 ID 사용, 비용·점수·역할·원격 URL·INP·파일경로는 입력 불가. 알 수 없는 필드·enum·중복 셀·면적 정밀도 위반 거부.

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
