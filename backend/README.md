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

## 기관 계정 승인

공개 가입은 PLAYER 고정. 먼저 해당 담당자가 가입한다. 운영자가 소속을 확인한 후 로컬 명령으로만 승인한다. `MFA_ENCRYPTION_KEY`에 Base64 32바이트 난수 키를 안전하게 설정하고 DB 백업과 별도 보관한다. 키 손실 시 MFA 재등록 필요.

```sh
./backend/mvnw -f backend/pom.xml package -DskipTests
# 대화형 터미널·DB 설정·MFA 키 필요. 인증 앱 등록 주소는 터미널에만 표시.
python3 scripts/run_local.py provision
```

명령은 기존 회원·기관을 확인하고 역할 승인, TOTP 비밀 AES-GCM 저장, 기존 세션 폐기, 감사 이벤트를 기록한다. 기본 기관이나 테스트 비밀번호를 제공하지 않는다. 로그인 시 기관은 비밀번호와 인증 앱 6자리 OTP가 모두 필요하다.
