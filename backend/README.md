# WATER LEAGUE API

Java 25·Spring Boot 4.1.1·PostgreSQL·Flyway·Spring Session JDBC. 계정·자료·모델·전략·계산·순위·연구 도메인, 내부 controller/dto/entity/repository/service/mapper/view와 공통 예외 핸들러.

```sh
# 저장소 루트, .env.local에 DB 설정 후
python3 scripts/run_local.py api
./backend/mvnw -f backend/pom.xml verify
```

기본 127.0.0.1:8080. local 프로필은 HTTP 쿠키, 기본 프로필은 `__Host-waterleague` Secure·HttpOnly·SameSite. Java 25 필수. 테스트는 H2 PostgreSQL 모드이고 운영 큐는 실제 PostgreSQL의 SKIP LOCKED 사용.

주간 설치·예산·재해 설계/게스트 계산·제출·기상·지도 API와 기관 연구 경로를 제공한다. endpoint·권한·한도는 [API 계약](../docs/06-api.md), 현재 화면 공개 범위는 [제품 계약](../docs/01-product.md)을 따른다. 과거 연구 큐의 한도를 모든 게임 작업에 일괄 적용하지 않는다.

모든 상태 변경은 CSRF·소유권·승인 상태를 검사하고 내부 오류/비밀을 공통 응답에서 제거한다. 실제 스키마는 SQL/Java Flyway migration이 기준이며 개요는 [데이터 모델](../docs/05-data-model.md)에 둔다.

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

리그 API·승인 API 상세: [계약](../docs/06-api.md), [회원 승인·보안](../docs/07-security.md).
