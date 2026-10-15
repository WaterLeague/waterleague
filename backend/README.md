# WATER LEAGUE API

Java 25·Spring Boot 4.1.1·PostgreSQL·Flyway·Spring Session JDBC. 계정·자료·모델·전략·계산·순위·연구 도메인, 내부 controller/dto/entity/repository/service/mapper/view와 공통 예외 핸들러.

```sh
# 저장소 루트, .env.local에 DB 설정 후
python3 scripts/run_local.py api
./backend/mvnw -f backend/pom.xml verify
```

기본 127.0.0.1:8080. local 프로필은 HTTP 쿠키, 기본 프로필은 `__Host-waterleague` Secure·HttpOnly·SameSite. Java 25 필수. 테스트는 H2 PostgreSQL 모드이고 운영 큐는 실제 PostgreSQL의 SKIP LOCKED 사용.

| API | 권한·기능 |
| --- | --- |
| GET `/api/v1/lab` | 고정 실험 모델·해시 |
| GET `/api/v1/catalog`, `/api/v1/maps` | 출처·승인 맵; 현장 승인 맵 없음 |
| GET `/api/v1/auth/csrf` | CSRF 토큰 |
| POST `/api/v1/auth/register`, `/login`, `/logout` | 회원 인증·세션 회전 |
| GET `/api/v1/auth/me` | 현재 회원 |
| GET/POST `/api/v1/strategies` | 내 설계 목록·생성 |
| GET `/api/v1/strategies/{id}` | 내 불변 버전 이력 |
| POST `/api/v1/strategies/{id}/versions` | baseRevision 충돌 검사·저장 |
| POST `/api/v1/simulations` | versionId·requestKey 멱등 큐 등록 |
| GET `/api/v1/simulations`, `/{id}`, `/{id}/bundle` | 내 계산·재현 파일 |
| GET `/api/v1/leaderboard` | 현재 모델의 제출 최고 기록 |
| POST `/api/v1/submissions` | 서버 품질·해시·점수 검증 |
| GET `/api/v1/organizations`, `/api/v1/consents` | 승인 기관·내 동의 |
| PUT `/api/v1/consents/{id}` | 기관별 동의·철회 |
| GET `/api/v1/research/strategies`, `/{id}`, `/{id}/bundle` | 기관 MFA·소속·동의·제출 버전 검증 |

모든 상태 변경은 CSRF 검사, unknown 필드·본문 64 KiB 초과 거부. 계산 사용자당 동시 3개·전역 500개, 시설당 서버 단가, 원화 비용 저장. 기관 상세에는 계정명·비밀번호·미제출 후속 버전 제외.

## 단일 관리자 초기화·회원 승인

역할은 ADMIN과 MEMBER. 회원 유형은 PLAYER·BUSINESS·INSTITUTION·GOVERNMENT다. 플레이어는 즉시 이용하고 기업·기관·정부 회원은 관리자 승인 전 업무 로그인 불가. 관리자는 연구 자료의 자동 열람 권한이 없다.

`MFA_ENCRYPTION_KEY`에 Base64 32바이트 난수 키를 기존 `.env.local`에 설정하고 DB 백업과 별도 보관한다. 관리자 최초 한 계정만 로컬 대화형 명령으로 생성한다. 이미 관리자 계정이 있으면 명령과 DB 유일 제약이 두 번째 계정을 차단한다.

```sh
./backend/mvnw -f backend/pom.xml package
python3 scripts/run_local.py provision
```

명령에 새 관리자 아이디·비밀번호를 직접 입력한다. 콘솔에 한 번 표시되는 TOTP 등록 정보를 관리자의 인증 앱에 등록한다. 명령줄 인수·환경 예제·Git에 비밀번호나 인증키를 넣지 않는다. 기본 관리자 계정·비밀번호 없음.

관리자로 로그인 후 **회원 관리**에서 신청 조직명·유형·이용 목적을 검토한다. 소속 확인을 마친 조직 회원을 승인하고 사유를 기록한다. 같은 이름의 조직도 자동 합치지 않으며 기존 조직 연결은 확인 후 명시적으로 선택한다. 반려·정지·재승인은 이력과 세션 폐기를 동반한다.

승인된 조직 회원은 로그인 과정에서 인증 앱을 직접 등록한다. 비밀번호 확인·5분 등록 세션·OTP 검증 전에는 업무 세션이 발급되지 않는다. 이미 등록된 키는 등록 API로 조회·덮어쓰기 불가. 관리자가 회원 OTP를 전달하는 이전 명령은 제거했다. 기존 조직 계정은 마이그레이션 시 PENDING으로 전환된다.

리그 API·승인 API 상세: [계약](../docs/06-api.md), [회원 승인 결정](../docs/decisions/0006-member-approval.md).
