# API·오류 계약

기준일: 2026-10-20. 현재 서버 계약이다. 연구/구형 설계 endpoint의 존재는 기본 UI 노출을 뜻하지 않는다. 아래 이전 schema 응답 설명은 현재 구현 사실이며 후속 구조 통합의 호환 의무가 아니다. 제품 규칙은 [제품](01-product.md), 확장은 [구현 목표](09-delivery.md)를 따른다.

## 설치 원가 기록 · 2026-10-18

- `GET /api/v1/installations/{id}/cost`: 현재 공개 설치의 설치 당시 원가 내역. `RECORDED`는 `sha256`과 `estimate`(후보 해시·시설·수량·단가·예산 반영액·출처·미산정 항목), `NOT_RECORDED`는 두 필드 null. 이전 설치에 현재 가격을 계산해 채우지 않음. 철거·없는 설치는 404, 원문 해시나 설치 정보 불일치는 공통 `COST_DATA_INVALID` 503. 별도 상세 조회로 전체 지도 설치 목록의 응답 크기 유지.
- 신규 주간 설치의 `cost_snapshot` 원문·SHA-256은 같은 트랜잭션에 저장. 재해 신규 요청은 각 배치의 `costSnapshotRaw`·`costSnapshotSha256`을 서버가 생성해 입력 해시에 포함. 클라이언트가 가격을 제출하지 않음. 같은 요청 키의 과거 실행은 기존 원문 반환.
- 워커는 설치 당시 후보/수량/시설/단가 자료와 스냅샷을 대조하고 원문을 `cost-snapshot.json`에 보존. 재해 결과의 시설별 `costRecord`는 검증한 같은 내역이며 기존 소유권·재현 다운로드 경계 적용. 완전한 공사비·가격 기준연도는 null, 현재/당시 가격 검증 여부 false. 기존 원화 예산 정책·단가·물리 계산 변경 없음.

## 공통 계약

공통 경로 `/api/v1`, 동일 출처 JSON, 서버 세션. 상태 변경 CSRF 필수. UTC ISO 8601·필드별 SI 단위. 금액은 KRW이며 면적×단가의 계산 비용·원장은 소수 둘째 자리까지 보존한다. 아래 표는 인증·연구 설계 API이며 공통 게임 API는 다음 절을 함께 본다.

새 원형 독립 표면 결과는 [공통 설계 계약](05-data-model.md#입력해시결과)의 `designContract`를 포함한다. 주간 `/installations/{id}/physics`는 `result.designContract`, 회원 재해 실험은 `result.facilities[].designContract`, 전체 사건 제출은 구별 결과의 시설에 같은 계약을 보존한다. 화면은 유출 비교와 평가 시각이 같은 계약에서 전체 표면/시설 면적·직접 강우 범위를 표시하며 불일치는 근거 미확인으로 처리한다. 게스트 최종 점수 잠금의 응답 허용 목록은 확장하지 않으며 과거 결과의 계약 결측은 0이나 현재 근거로 채우지 않는다.

현재 독립 표면의 `runoffComparison`과 공개 연구 관망의 `result`는 스키마 v2에서 `metricComparison`을 필수로 보관한다. 그 값은 `SIGNED_ABSOLUTE_PRIMARY_RELATIVE_AUXILIARY_V1` 원 지표 계약이다. 지표별 단위·경계·기준/설계 원값·부호 있는 절대 개선량·보조 개선율과 비교/미산정/보류 사유를 제공한다. 0·음수 기준의 비율은 null이며 절대 차이를 없애지 않는다. 연결되지 않은 관망/지표·미수집 지속시간·미확보 사용 수요는 null과 사유를 보존한다. 새 구형 RB LID 계산은 덮개 강우 우회 미계산으로 효과 비교를 보류하고 기존 두 변화량 필드도 null로 반환한다. 수치 검사 상태·원 계산값·과거 산출물은 유지하며 종합점수·비율 순위를 만들지 않는다.

주간 구/개인 기록의 `scoreM3`는 평가 초가 0이면 null이며 순위도 null이다. 실제 평가를 거친 0과 음수는 수치로 반환한다. 일부 구간만 계산했으면 해당 구간의 부호 있는 합계와 평가/예상 초를 함께 제공하며 전체 구간 완료 전 우승 확정은 기존대로 금지한다.

| API | 권한·역할 |
| --- | --- |
| GET /auth/csrf | 공개, CSRF 발급 |
| POST /auth/register, /auth/login | 공개+CSRF, 유형별 가입·승인 상태·세션 회전 |
| POST /auth/logout, GET /auth/me | 인증, 세션 폐기·본인 요약 |
| GET /catalog, /maps | 공개 자료 목록·승인된 공식 맵 목록 |
| GET /lab | 탐색 모델·셀·분강우·단가 근거·모델 해시 |
| GET /spatial/buildings | 인증, 보관한 2025 수치지형도 건물 스냅샷·해시 검사; no-store·외부 호출 없음 |
| GET /spatial/play | 공개 원형 계산 자료의 해시·공통 조건·출처·정책; no-store |
| GET /spatial/play/sites | 공개, 절대 EPSG:5186 범위의 전체 원형 후보 조회 |
| GET /spatial/play/sites/{districtId}/{candidateId} | 공개 행정코드·후보 ID로 같은 원형/계산 조건 조회 |
| GET /spatial/play/forcings | 원형 공간의 공개 행정구·보관 관측 창·재해/선행 기상 결속 목록·해시; no-store |
| GET /spatial/play/forcings/{modelHash} | 등록된 불변 관측 입력 조회; 공간 후보·물리 모델과 분리 |
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
| GET /facilities/epa-designs-v1 … v4 | 해시 고정 공개 시설 제원·문헌 범위·출처, ETag·공개 캐시 |
| GET /organizations | 승인된 기관 목록 |
| GET /consents, PUT /consents/{organizationId} | 본인 기관별 동의 조회·부여·철회 |
| GET /research/strategies | MFA 인증 승인 기관, 동의된 현재 모델 제출 최대 100건 |
| GET /research/strategies/{jobId} | 승인 기관·동의, 제출 버전까지 이력과 계산 당시 모델 |
| GET /research/strategies/{jobId}/bundle | 승인 기관·동의, 재인가 후 재현 ZIP |
| GET/POST /research/comparisons | MFA 승인 조직의 동의된 제출 다강우 재계산 목록·생성, 기관별 멱등키 |
| GET /research/comparisons/{id} | 현재 원본 동의·조직 승인 재검사, 원본과 파생 계산 결과 |
| GET /research/comparisons/{id}/jobs/{jobId}/bundle | 현재 동의·기관 분석 그룹 연결 검사, 목적과 원본 연결 포함 ZIP |
| POST /research/patterns | 동일 모델의 동의 제출 1~50개, 상위 고유 설계 1~20개와 경계 동점의 배치 기술 통계 |

모델 검증·배포 권한은 조직 회원의 리그 운영과 분리. 내부 워커 endpoint 외부 노출 금지. 현장 승인 맵과 공개 참고 지도·탐색 모델은 구분한다. 관리자 역할은 ADMIN, 모든 일반/조직 회원 역할은 MEMBER. 조직 회원의 연구·리그 권한은 승인 상태·회원 유형·소속·MFA로 검사한다.

원형 조회의 `minx,miny,maxx,maxy`와 응답 `geometry`는 절대 EPSG:5186 미터 좌표다. 시야의 가로/세로는 각각 2,000m 이하, `limit` 기본 512·최대 2,000이다. 선택 `districtId`는 공개 자치구 코드, `kind`는 ROOF/GROUND다. `includeUnsupported=false`가 기본이며 true일 때 빈 허용 목록의 미지원 표면도 조회한다. 구멍/다중 면을 보존한 실제 도형으로 교차 판정한다. 범위 인덱스 검사 20,000개·본문 처리 16MiB·결과 한도를 넘으면 일부를 정상 목록으로 반환하지 않고 `SPATIAL_VIEW_TOO_DENSE` 422를 반환한다. 접속 주소별 분당 300회·동시 시야 조회 4개 상한과 429 응답을 적용한다. 모든 응답의 `catalogSha256`은 같은 불변 원형 DB를 가리킨다. 현재 주간·재해 설치/제출은 같은 원형 DB 해시와 공개 5자리 구 코드를 사용한다. 설치 후보 ID는 `C`와 소문자 16진수 24자리다.

관측 결속은 별도 `catalogSha256`과 `siteCatalogSha256`으로 관측 창 목록과 원형 DB를 각각 고정한다. 25개 구별 기본 창 1개·재해 3개, 총 100개이며 `modelHash`는 관측 결속 원문의 해시다. 재해는 같은 지점의 7일 선행 관측이 보관된 경우만 선택한다. 관측 창별 보관·검사 통과 지점 안에서 공개 구 대표점과 10km 이내 최근접을 선택하며, 전체 AWS 중 최근접·현장 강우 대표성·사건 당시 지형 복원을 뜻하지 않는다. 후보 셀이나 OSM 모델을 관측 결속에 포함하지 않는다. 등록되지 않은 해시는 `MODEL_NOT_ELIGIBLE` 422, 잘못된 해시 형식은 `REQUEST_INVALID` 400, 접속 주소별 분당 300회 초과는 429다. 현재 재해/주간의 관측 결속은 이 목록을 사용하며 공간 형상과 별도 해시로 관리한다. 현재 게임 데이터셋은 `SEOUL_NGII_GAME_V2`다.

공동 시설 물리 상태는 `WAITING/RUNNING/READY/DELAYED/UNAVAILABLE`. `attemptedAt`과 `simulatedThrough` 구분, 실패 시 이전 성공 결과와 그 시각 유지. 무결과는 `result:null`이며 강우·수분·유출 0 대입 없음. 마지막 계산이 5분을 넘으면 지연 표시, 실행 작업이 240초를 넘으면 보류 표시. 결과는 관측소·계산 구간·EPA 버전·EXPLORATORY·누적 강우 체적/침투/증발/유출·현재 수분/저류·시설 표면 수심·토양수분·물수지 오차·증발/초기상태 가정만 공개. 원문·파일 경로·입력 hash·임대 토큰 미노출. 철거·미등록 시설 404. 분별 재현 입력은 별도 접근 통제 대상이며 이 공개 요약에서 제공하지 않음.

## 공통 게임 API

| API | 현재 계약 |
| --- | --- |
| GET /installations | 활성 주간 시설·공개 닉네임·위치·이번 주 점수/평가 시각. 계산 전 점수는 null |
| GET /installations/sites | 구·시야 x/y·offset·시설 type·vacant·surface로 후보 조회 |
| GET /installations/sites/{districtId}/{cellId} | 공개 후보 상세 |
| GET /installations/sites/{districtId}/building | 원 건물 sourceId로 후보 조회 |
| GET /installations/sites/ground | 화면 상대 미터 x/y의 실제 점을 포함하는 후보·정규 소속 구 조회 |
| POST /installations | 로그인·소속 구·본인 중복·면적·시설·예산·CSRF 검사 후 확정 |
| DELETE /installations/{id} | 소유자 검사. 현재 주 잠긴 확정 시설의 취소 거부 |
| GET /rainfall/live | 구별 현재 관측·유효 시각·결측 상태. 실제 무강우와 미확인 구분 |
| GET /weekly, /budget | 주간 순위/기여와 개인 예산. 상세는 아래 계약 |
| GET/POST /guest-historical | 비회원 세션별 실험·진행 전용 결과. 제출·최종 점수 제외 |
| GET/POST /historical | 회원 소유 재해 실험·결과 |
| GET/PUT /historical/designs/{eventId} | 회원 재해 전체 구 설계·revision |
| POST /historical/designs/{eventId}/submissions | 최신 저장본과 hash를 동결한 사건 전체 제출 |
| GET /historical/leaderboard/{eventId} | 인증된 회원의 사건별 최종 기록 경쟁 |
| GET /surface/current | `index,minX,minY,maxX,maxY`로 현재 공개 지표 실행 목록 조회 |
| GET /surface/current/{id}/frame | 같은 필수 범위/프레임 입력으로 공개 실행 프레임 조회 |

현재 공개 지표 registry의 `models`는 비어 있다. API가 존재해도 서울 전역 실시간 침수 결과가 제공된다는 뜻은 아니다. 원자료/운영 모형의 검증과 등록은 [확장 계획](09-delivery.md)에 둔다.

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

리그 초안 추가 입력: `placementLimit`(배치 구역 수), `areaLimitM2`(합산 면적, 소수 두 자리), `award`(`prizeKrw`, `winnerCount`, `notice`). 참가 규칙을 포함한 schema 3에도 포함하며 공개 후 고정. 필드 생략 시 모델 상한·상금 없음 적용, 기존 버전 1 규칙 원문·hash 유지. 제출은 저장 배치의 개수·면적을 서버에서 재검사하며 초과 시 422 `LEAGUE_RULES_MISMATCH`. [제한·상금 계약](17-league-participation.md) 참조.

## 리그 참가·팀전 서버 API

schema 3은 초안에 `participation: {access, admission, entryMode, teamSizeLimit}`를 포함. 값·이전 규칙 호환·개인/팀 한도는 [참가 계약](17-league-participation.md) 참조. 기관 리그 초안 구성요소는 schema 3 참가 방식을 명시하며 기존 schema 1/2 규칙은 그대로 열람·제출.

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

계산별 불변 요청, 소유자 승인/거절/철회, 기관 검토 이력, 커서 목록·목적별 재현 ZIP은 [활용 계약](16-utilization-consent.md) 참조. 연구 동의와 사업 활용 검토 동의는 독립 범위이며, 사업용 다운로드는 지정 요청의 승인 상태·계산·기관·소유자 상태를 준비 전후 확인한다. 관리자에게 자료 접근 권한을 부여하지 않는다.

기관 재계산·패턴 통계의 요청/응답·권한·원본 소유권·한도·철회 계약은 [기관 분석 계약](18-institution-analysis.md) 참조. 서로 다른 모델의 패턴 혼합은 `ANALYSIS_INCOMPATIBLE` 422, 원본 미동의·타 조직 그룹은 404. 생성은 202, 동일 키/다른 내용 409, 활성 계산 한도 초과 429. 모든 분석 응답은 no-store.

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
| 422 | PLACEMENT_INVALID, BUDGET_EXCEEDED, MODEL_NOT_ELIGIBLE, RAIN_QUALITY_FAILED, SPATIAL_VIEW_TOO_DENSE |
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

공개 연결 관망 연구 API는 `MEMBER` 인증·현재 승인 상태와 기존 CSRF 검사를 적용한다. `GET /api/v1/watersheds/catalog`는 불변 카탈로그 원문·SHA-256, 실제 공개 연구 관망의 14집수 면적/출구·4종 문헌 제원·미확인 조건 제공. `POST /api/v1/watersheds`는 `requestKey`, `catalogHash`, `placements[{id,catchmentId,facilityType,areaM2,treatedImperviousM2}]`를 받아 202 반환. 시설 면적 전체를 불투수 면적으로 대체하는 이 버전의 규칙과 서버 제원·시드를 고정하며, 같은 집수의 시설/처리 면적 합산·중복 ID·소스 해시·회원별 2개/전체 공용 20개 큐 한도 검사. 요청 키의 입력 변경은 409. 가격·소속 구 점유·주간 예산 차감 없음.

`GET /api/v1/watersheds`는 본인 최근 50작업, `GET /api/v1/watersheds/{id}`는 본인 입력과 결과 조회. `SUCCEEDED`는 보고서 생성 완료이며, 수치 품질은 결과 `numericalStatus`로 별도 확인. 수치 실패는 두 조건과 원 파일을 보존하고 `signedReductionM3:null`; 음의 개선량·방류 증가 보존. 월류를 지표 침수나 총점으로 전용하지 않음. `GET /api/v1/watersheds/{id}/bundle`는 소유자 전용 원본/파생 INP·RPT·OUT·관망/시설 상태·변환/입력·엔진/소스·재생 코드 묶음. DB 결과에 고정된 파일 해시와 내용 대조, 64MiB 파일/ZIP·512MiB 총량 제한, 경로 이탈·심볼릭 링크·입력/결과/목록 동시 변조 거부. 같은 플랫폼에서 새 출력 폴더로 `python replay.py --output <새 폴더>` 실행 시 두 OUT의 원 해시 대조. 좌표계/수직 기준 미확정으로 지리 배치·당시 재현·순위 미개방.

- `GET /api/v1/disasters`: 공개 재해 3건과 각 사건의 25개 구 강우 모델·시각·관측소·분량 제공.
- `POST /api/v1/historical`: 로그인 회원의 선택 구·등록 재해 모델·공개 후보 1~50곳 검사 후 계산 요청. 요청 키 재사용은 같은 입력에만 허용. 다른 구 연구 허용, 공동 위치 점유 변경 없음.
- 선택 `sensitivityCellId`는 같은 요청 배치 중 한 곳만 지정. 선행 초기화·제원 지원 후보인지 서버 확인 후 배치의 `initializationSensitivity=SELECTED_SURFACE_7_DAY_DRY_WET_V1` 정책을 입력 해시에 고정. 식생수로의 신규 요청은 `SELECTED_SWALE_7_DAY_STATE_V2`로 고정하여 단일 빈 표면·기본 침투 상태만 계산하고 `seedPolicy=NOT_APPLICABLE_FIXED_EMPTY_SURFACE`·빈 건습 차이 목록 반환. 워커는 시설과 정책 불일치 거부. 같은 요청 키로 비교 대상 추가/제거/변경 시 409, 미배치 대상 거부. 기존 입력의 멱등 재시도는 원 기록 반환. 별도 비교 요청이 없는 기존 계산은 추가 실행 없음.
- 결과의 선택 `initializationSensitivity`는 동일 7일 관측과 건조/포화 시드의 평가 시작 상태·평가 지표·차이·조건별 성공/실패 보고서. 식생수로 v2는 단일 시작 상태·원 지표만 반환하며 건습 차이 목록은 빈 배열. 조건 실패 시 `comparison.status=INCOMPLETE`, 범위·차이 null. 일반 결과·순위에 비교 효과 합산 없음. 소유자 전용 재현 ZIP에 `sensitivity/`의 원 입력·계산·실패·해시 포함, 기존 경로/크기/변조/심볼릭 링크 차단 유지.
- `GET /api/v1/historical`, `GET /api/v1/historical/{id}`: 요청자 본인의 비공개 작업 목록·상태·결과.
- `GET /api/v1/historical/{id}/bundle`: 본인 성공 작업의 해시 검증된 재현 묶음. 경로 이탈·심볼릭 링크·파일 변조 차단.
- `POST /api/v1/historical/designs/{eventId}/submissions`: 본인 최신 저장본의 `requestKey`, `revision`, `snapshotSha256`만 입력. 서버가 불변 저장본의 전체 구 배치·원 설치 시각·원가를 가져와 사건 전체 기간 제출로 생성. 인증·CSRF·회원별 시간당 20회 제한·no-store 적용. 저장본 변경은 `HISTORICAL_DESIGN_CONFLICT` 409, 현재 형상/가격/정책 변경은 `HISTORICAL_SITE_CHANGED` 409, 다른 소유자의 설계는 조회 불가. 기존 요청 키 재전송은 이후 편집에도 원 제출 반환. 응답 `designRevision`은 구형 제출에서 null이며 기존 `/historical/submissions`와 원 요청·비용·결과 보존. 재현 묶음은 고정한 `submission-design.json` 해시 추가 검사.

재해 설계 예산은 회원당 20억 원이며 여러 구의 설계 초안을 합산. 서울시 빗물관리시설 전체 사업 규모를 개인에게 적용한 게임 규칙으로 실제 지급액이 아님. 결과는 선택 표면의 기준 대비 유출·배수·순저류 체적 비교. 관망·실제 침수 복원 결과로 확대 해석 금지.

## 공동 주간 순위

`GET /api/v1/weekly`는 이번 주·지난주의 25개 구 합계, 개인 상위 100명, 로그인한 본인의 전체 순위, 주간 종료 시각과 확정 우승 구를 제공. 한국시간 월요일 경계, 동점 공동 순위, 음수 기여 보존. 계산 완료 분 수와 설치 이후 예상 분 수가 다르면 종료 주 `PROVISIONAL`; 빈 주 `EMPTY`, 완료 주 `FINAL`. 실제 자료 없는 가상 순위 금지. 2분 처리 여유를 둔 목표 시각·생성 시각·탐색 등급 표시. 응답의 본인 기록에 계정명·이메일·인증 정보 제외.

## 공동 배치예산·시설 비용

`GET /api/v1/budget`는 `policy`(사업 총액 `limitKrw`·개인 한도 `personalLimitKrw` 각각 20억 원, `allocationScope=MEMBER`, 참고연도·출처·원문 해시·규칙 버전), 본인 활성 설치 비용 `allocatedKrw`, `remainingKrw`, `personal`을 반환. 익명은 사용액 0·한도 미리보기·`personal=false`; 다른 회원의 잔액 제공 없음. 본인 ID는 서버 인증에서 결정. 설치·철거 트랜잭션의 회원 행 잠금으로 동시 초과 지출 차단. 주간은 소속 구를 검사하며 본인 중복만 차단한다. 서로 다른 회원은 같은 위치에 독립 설치할 수 있다. 현재 주 확정 시설의 취소는 거부한다. 규칙 `SEOUL_PERSONAL_FULL_2026_V3`를 신규 설치 행 `budget_policy`와 재해 요청에 고정. 이전 구별 8천만 원 규칙은 기존 기록 재현에만 보존. 후보의 시설 단가·포함/제외 범위·출처와 저장 설치 비용은 변경하지 않음.

예산 원장 확장 계약: 같은 응답의 `accounting`에 버전·사업군 한도/사용액/잔액·시설별 사용액/가용액 반환. 현재 일반 설치 6종은 같은 빗물관리 사업군의 20억 원을 공유하며 시설별 별도 한도는 `null`(별도 배정 없음). 가용액은 시설 잔액과 상위 사업 잔액 중 작은 값이며 시설별 가용액 합계를 전체 재원으로 표시하지 않음. 기존 설치의 원 비용·원 예산 정책·설치/취소 시각을 원장에 이관, 이관 기록임을 구분. 새 설치/취소는 회원 잠금과 같은 트랜잭션에서 한 번씩 기록, 실패 시 원장도 롤백. 취소는 가상 설계 배정의 해제이며 실제 공사비 환급이 아님.

`GET /api/v1/budget/ledger?beforeId=<커서>`는 인증된 본인의 원장만 50건씩 역순 조회. 시설·사업·설치 ID·배정/취소·원 비용·실제 발생/기록 시각·이관 여부·원 예산 정책을 제공. 수정/삭제 API 없음, 익명 조회 거부·타 회원 ID 입력 불가·`Cache-Control: no-store`. 재해 계산은 주간 원장을 차감하지 않고 같은 사업/시설 한도 규칙으로 별도 설계 비용을 검사하며 입력에 해당 원가/예산 집계를 고정. 사건 당시 예산의 검증 완료를 뜻하지 않음.

## 공동 설치 연구 기록

`GET/PUT /consents/shared[/{organizationId}]`는 기존 전략 동의와 독립적인 기관별 공동 설치 연구 동의. `GET /installations/records`와 `/installations/records/{jobId}[/bundle]`는 본인 완료 기록. `GET /research/installations` 및 `/research/installations/{jobId}[/bundle]`는 승인된 조직 회원의 현재 기관에 동의된 기록. 목록은 한국시간 주 시작일의 기여·회원 합계 순으로 최대 100개 설치, 상세는 선택한 완료 job에 고정. 이메일·사용자명·IP·키 미포함. 산출물 manifest의 DB 고정 해시·입력 해시·모델/설치 연결 검증 후 다운로드, 과거 manifest 미고정 작업은 내보내기 보류.

상세는 DB에 고정된 manifest SHA-256과 요청·모델·설치 연결을 검사한 완료 작업만 제공. 설치 이후 누적 수문 상태와 주간 합계를 구분하며 화면은 최대 360개 시점을 추출, 원본 분별 결과는 재현 묶음에 보존. 초기 수분·저류, 최종 저류, 순저류 변화 분리. 원문 강우·기상은 계산 연장 시 이전 구간에서 함께 복사하고 원문 누락 여부를 명시. 조회 가능 주는 한국시간 현재 주 이하의 월요일 시작일. 화면 비활성화·조회 범위 변경 시 상세 제거, 복귀·30초 갱신 시 권한 재확인.

계산 원문은 SHA-256별 불변 원본을 프로젝트에 보관하고 각 계산 디렉터리에 하드 링크로 연결. 링크 미지원 저장소는 검증 후 복사. 외부 심볼릭 링크는 거부하며 원문 변경 시 조회 차단. 내보내기의 주간 원문 증가를 수용하도록 manifest 8MiB·최대 50,000개, 합계 원본 512MiB, 개별 파일 64MiB·ZIP 64MiB 제한 적용. 한도를 넘는 파일은 불완전한 묶음 대신 제공 보류.

신규 후보 v5 응답의 `facilityDesignSet`은 공개 제원 ID·SHA-256, `initializationPolicy`는 7일 선행 계산 정책. 물리 상태 응답과 재해 시설 결과의 `initialization`은 시작 토양수분·저류량, 선행 강우 총량·기간, 원문 해시, 구간 평균 적용 분 수와 한계를 포함. 해당 값은 관측 기반 계산이며 토양수분 실측값으로 표시하지 않음. 기존 버전 기록에는 새 초기 상태를 소급 생성하지 않음.

공동 설치 연구 상세의 `initialization`·`facilityDesign`은 manifest 검증을 통과한 해당 작업의 `result.json`에서 반환. 현재 제원 목록이나 DB 요약으로 대체하지 않으며 보관 근거가 없는 기존 기록은 null 반환. 물리 상태·재해 결과·기관 연구 화면은 같은 제원 표시 컴포넌트로 매개변수별 문헌 범위·설계 가정·원문 해시 표시. 본인·현재 기관별 동의·계정 상태 검증 유지.

공동 설치 연구 상세의 `budgetLedger`는 선택한 설치 1건의 원장 조회본. `capturedAt`·`evaluatedThrough`·설치 당시 비용·원 정책·배정/취소 발생 및 기록 시각·이관 여부 제공. `allocatedAtEvaluationKrw`는 실제 이벤트 발생 시각이 계산 종료 시각 이하인 원장 합, `allocatedAtCaptureKrw`는 조회 당시 해당 설치의 순배정액. 이후 취소를 계산 당시 배정액에 소급하지 않음. 전체 회원 지갑·다른 설치의 비용/정책 미포함. 원장이 없는 이전 기록은 `NOT_RECORDED`·금액 null, 설치 비용과 원장 금액/시설/시각/취소 연결이 다르면 503 `BUDGET_DATA_INVALID`. 실제 공사비 집행·환급이나 당시 원장 저장 상태의 완전 복원으로 표시하지 않음.

공동 연구 ZIP은 원 물리 `manifest.json`·파일을 그대로 유지하며 `budget-ledger.json`(다운로드 시점 조회본)·`export-manifest.json` 추가. 내보내기 목록은 원 물리 매니페스트 SHA-256과 원 파일·원장·접근 범위 각각의 해시 포함, 자체 파일 해시는 제외. 원 산출물에 내보내기 예약 파일명이 있으면 거부. 원장/메타자료 추가는 원 물리 계산 해시나 점수 변경이 아님. 목록·상세·ZIP의 기존 동의·승인·MFA·조회 전후 재인가 유지, 동의 철회 후 추가 조회/다운로드 차단.

### 공개 기존 시설 참고 카탈로그

`GET /api/v1/infrastructure/seoul-native-infrastructure-20261020-v1`은 비회원 조회 가능. 공개 위치점 원본 9종·1,696기록 중 표시 가능한 1,604기록을 반환한다. 삭제 90건·위치/상태 미확인 2건을 보존하고 외부 API를 호출하지 않는다. `usage=REFERENCE_ONLY`, 운영 미확인·유효 시작/끝 null·관망 미연결·수직 층위 UNKNOWN이다. 현재 확인된 시설 부지 도형은 0개다. ETag·공개 불변 캐시를 제공하며 원문 속성·로컬 경로는 노출하지 않는다. 강서구 양수량 단위 m³/min·시설별 유수지 용량과 광진구 공개 설비 이력의 원문 대응을 유지한다. 이전 OSM 도형 목록은 보관 근거이며 현재 조회의 대체 입력으로 사용하지 않는다.

후보의 선택적 `referenceInfrastructure`는 공개 위치점이 실제 후보 도형 안에 포함된 대응 1,104건이다. 부지·시공 가능성·운영·과거 존속 확인이 아니므로 설치 제외·점유로 사용하지 않는다. 당시 참고 정책의 버전·원문 해시·공간 해시는 설치 `admission_snapshot`과 재해 입력의 `publicAssetPolicy`에 고정한다. 현재 `exclusions`는 빈 목록이며 위치점 근접만으로 이전 `EXISTING_INFRASTRUCTURE` 차단을 유지하지 않는다.

### 지표 수심·속력 결과 조회

- `GET /api/v1/historical/{id}/surface/catalog|frame`: 본인의 성공한 재해 실행.
- `GET /api/v1/installations/{id}/surface/catalog|frame`: 본인 설치의 최신 성공 실행.
- `GET /api/v1/installations/records/{id}/surface/catalog|frame`: 본인의 고정 실행 기록.
- `GET /api/v1/research/installations/{id}/surface/catalog|frame`: 승인 기관·MFA·현재 공유 연구 동의가 있는 실행 기록.
- `catalog`는 원 계산/카탈로그 해시·실제 기록 시각·EPSG:5186 지도 원점·계산 등급·한계 반환. `frame`은 `index,minX,minY,maxX,maxY` 필수. 화면 좌표는 도시 공통 원점 이동 후 미터이며 원 계산 경계와 별개. 선택 시각 하나의 원 수심/운동량을 읽고 영역과 교차하는 격자의 수심·속력·도형 반환. 8,192격자 초과는 413이며 임의 생략 없음.
- 요청마다 파일 조회 전후 소유/기관/동의 재검사, `no-store`, 회원당 분당 120요청. 게시된 지표 결과가 없으면 404; 다른 시설의 내부 수심을 지표 침수로 대체하지 않음. 파일 변조·심볼릭 링크·물수지 불일치는 공통 오류로 거부, 내부 경로 비노출.
- 작업 결과의 선택적 `surfacePlayback` 참조는 `schemaVersion:1,catalogSha256,surfaceResultSha256`로 고정. 해당 작업의 서버 lease 디렉터리 아래 `surface-playback/`만 조회. 클라이언트 경로·파일명·원본 URL 입력 금지. 현재 기존 시설 유출 작업에는 이 참조가 없으며 연결 유역 작업의 생성·게시 연동은 별도 진행.


### 빗물이용조 지도 초안

`GET|POST /api/v1/installations/cistern-plans`, `DELETE /api/v1/installations/cistern-plans/{id}`는 사용 가능한 MEMBER의 본인 계획에 한정. 현재 초안 POST는 소속 구·지붕/지상 후보 종류·원본 해시·공개 면적·공개 저류 영역·현재 공유 설치 점유 검사. 면적 소수 둘째 자리·깊이 소수 셋째 자리 입력, 깊이 100m는 입력 범위 방어이며 현장 설계 허용치가 아님. 본인 잠금과 활성 입력 해시 고유 제약으로 동시 재시도에 같은 계획 반환, 활성 계획 20개 한도. 삭제는 원 스냅샷을 보존하는 논리 삭제.

응답의 `snapshot`은 두 후보 원 자료·설계 입력·단면적×깊이 용량·수평 중심 거리·공개 용량 참고 견적을 고정하며 `inputHash`는 저장 JSON 바이트의 SHA-256. 조회 때 해시 재검사, 클라이언트도 위치·원본 해시·용량·견적의 결속 검사. `status=SPATIAL_DRAFT_NOT_INSTALLED`, `installationReady=false`, `positionReserved=false` 고정. 주간·재해 공통 계획이며 특정 사건 당시 시설 복원·설치·계산 작업을 생성하지 않음. 기존 설치·예산·점수와 분리된다. 실제 설치로 완성할 때 재해의 소속 구 제한 제거까지 [P2 완료 조건](09-delivery.md#p2--빗물이용시설-완성)에 포함한다.


지도 계획 POST의 선택적 `tankLayout`은 내부 `widthM`, 벽 `wallThicknessM`, 후보 중심에서의 `offsetXM/offsetYM`, 지도 가로축 기준 반시계 `rotationDeg`를 받는다. 전체 유효성·정밀도와 원 도형 포함 검사 후 `schemaVersion=2` 및 계산한 `tankGeometry`를 고정 저장. 클라이언트가 전송한 임의 외곽 좌표를 신뢰하지 않는다. 값이 없는 기존 요청은 같은 v1 직렬화·해시·재시도 반환을 유지하며 v1 응답에는 형상 없음. 새 화면의 저장은 유효한 외곽 배치를 요구한다. 기초/여유고·구조·수리 연결을 검사한 설치 API가 아니며 위치 점유·예산 지출 없음.


2026-10-19 비회원 재해 체험: GET/POST `/api/v1/guest-historical`, GET `/api/v1/guest-historical/{id}`만 익명 허용. POST는 CSRF 필수. 소유권은 서버 세션 ID의 해시로 고정하고 외부 owner/guest 식별자 입력 금지. 전체 사건 설계(여러 구 최대 50곳)를 검증한 후 선택 구를 기존 SWMM 큐에 등록. 회원 행·원장·제출 생성 없음. 동일 세션/요청 키는 전체 설계가 같을 때만 재사용. 회원 작업과 전역 admission 잠금을 공유, 세션 동시 2개·전체 20개 및 세션/네트워크/전역 시간당 호출 한도. 세션 종료 후 이전 게스트 결과 조회 불가, 재현 원본은 불변 보존. 제출/다운로드·`/historical/leaderboard/{eventId}`는 기존 회원 보호 경로. 비회원은 주간 설치 불가.


2026-10-19 지도 점수 응답: GET `/api/v1/installations`에 `scoreM3`(이번 KST 주간 서버 계산값, 미반영 null), `evaluatedThrough`(반영 원시각, 미반영 null) 추가. 기존 공개 설치 소유자 닉네임·위치 조회 권한 유지. 점수는 활성 시설에 대해 일괄 조회하고 클라이언트가 생성한 효과 수치 사용 금지. GET `/api/v1/rainfall/live`에 `windDirectionDeg`(AWS WD10, 0~360 또는 null) 추가. 360 무풍 코드는 시각 유향으로 변환하지 않으며 기존 WS10 풍속·관측 시각과 같은 행을 사용한다.

게스트 재해 GET 목록·개별 조회·POST 멱등 재응답은 진행 전용 결과를 반환한다. 최초 생성 응답도 DB 저장 행을 사용하여 PostgreSQL의 마이크로초 시각과 재요청 응답을 일치시킨다. 사건 전체 합계 3종·시설별 전체 기간 유출 비교·마지막 시계열 구간은 서버에서 제외한다. 원 계산 결과와 재현 원본은 DB에 보존하고 로그인 후 제출·최종 기록 경로는 기존 소유권·CSRF 검증을 유지한다.

## 도시 현재 표시 자료 (2026-10-19)

`GET /api/v1/urban/live?places=POI001,POI068`은 비회원 조회, IP당 분당 30회, ID 1~6개·중복/미등록 ID 거부, `Cache-Control: no-store`. 고정 카탈로그 해시·공식 출처 URL·장소별 인구/도로 값을 반환한다. `population`은 `minimum/maximum/sourceHourKst/congestion/retrievedAt/validUntil/sourceSha256`, `traffic`은 `speedKmh/observedAt/retrievedAt/validUntil/sourceSha256`. 인구의 조회 시각을 관측 시각으로 제공하지 않는다. 인구/교통 실패 필드는 각각 null과 일반화한 상태 코드이며 외부 HTML·내부 예외·키·URL 쿼리를 응답에 전달하지 않는다. 과거 사건 계산·점수·랭킹 입력에 사용하지 않는 현재 표시 자료다.

현재 원형 지상 선택: `/installations/sites`의 `surface=ROADWAY|WALKWAY|OTHER`는 각각 원 도로면·보도·그 외 원형 역할을 필터링하며 미지정은 전체다. `/installations/sites/ground?x=...&y=...`는 도시 원점 `[198128,551989]`에서 이동한 미터 좌표의 점을 포함하는 실제 지상 후보와 정규 소속 구를 반환한다. 클릭 지점의 행정구를 후보의 소속으로 강제하지 않는다. 후보 소속은 전체 형상의 최대 양의 구 교차 면적 규칙을 유지한다. 유한 좌표·범위를 검사하고 구멍·수면·제외 영역·먼 위치는 404다. 다른 후보까지 30m 확장하지 않는다. `/building?sourceId=ngii:{layer}:{sha256}`는 동일 원 객체의 옥상 후보를 조회한다. 과거 OSM `/street`·`/parking` 조회는 현재 제공하지 않는다. 시설 확정의 소속·시설 유형·면적·예산·CSRF는 서버에서 재검사한다.
