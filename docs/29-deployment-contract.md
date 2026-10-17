# 컨테이너 배포·로컬 HTTPS 검증 계약

2026-10-17. 문서 07·10의 비밀 분리·권한·복원 기준을 실행 가능한 배포 구성으로 연결. Oracle 접속/도메인은 사용자 확인 대기. 컨테이너 로컬 검증을 실제 Oracle 배포·부하·외부 백업 완료로 표시하지 않음. 모델은 기존 EXPLORATORY 유지.

## 구성과 권한

- 공식 이미지의 버전·다중 아키텍처 manifest digest 고정. Java 25 LTS, Node 24 LTS, 프로젝트가 지원하는 Python 3.14, PostgreSQL 18, Caddy 2 사용. amd64/arm64 빌드와 SWMM 수치 재현은 각각 실행 증거 필요.
- 프록시/정적 앱만 호스트 포트에 연결. 기본 검증 바인딩은 `127.0.0.1`, DB·API·워커는 포트 게시 금지. 프록시-API와 DB 네트워크 분리, 워커의 외부 네트워크 접근 제거.
- API·워커 비root·read-only 루트·capabilities 제거·no-new-privileges·프로세스/CPU/메모리 제한. 작업 산출물은 워커 쓰기·API 읽기 전용, 캐시는 워커 전용. 마이그레이션·볼륨 초기화는 일회성 별도 서비스.
- DB 소유/마이그레이션, API, 워커 자격 분리. API는 필요한 업무 테이블 DML, 워커는 두 큐의 claim/lease/result 열과 배치 읽기만 허용. 워커의 회원·비밀번호·MFA/동의·기관 변경, API/워커의 DDL·역할 생성 금지. 새 마이그레이션 후 명시적 권한 목록 재검사.
- DB 초기화와 마이그레이션은 실패 시 API/워커 시작 중단. 기존 DB/볼륨을 재초기화하거나 운영 자료를 시험 DB에 덮어쓰지 않음.

## 비밀과 이미지

기존 개발 `.env.local` 유지. 운영/시험 비밀은 별도 비공개 디렉터리의 파일로 생성하고 Compose secret mount로 서비스별 최소 전달. 이것은 새 개발 `.env` 파일이 아니며 실제 값·키는 Git/이미지/명령 인자에 포함하지 않음. 파일 기반 Compose secret은 호스트 파일의 암호화를 보장하지 않으므로 호스트 권한/디스크 암호화·외부 키 보관은 운영 게이트.

API는 Spring config tree, 워커는 `_FILE` 설정으로 DB 연결 비밀을 읽고 값 출력 금지. 개발 KMA/VWorld 키는 기본 이미지/실행에 포함하지 않음. 모델·원자료 수집과 고정 모델 계산 배포 분리. `.dockerignore`로 `.env*`, `.git`, 개인정보/원자료/계산 파일/로그/IDE 파일 제외, 필요한 공개 고정 모델·출처만 명시적으로 복사.

파일 기반 Compose secret의 uid/gid 옵션은 bind mount에서 적용되지 않을 수 있으므로 실행 사용자는 호스트의 비root UID/GID와 일치. 상태 폴더 0700·비밀 파일 0600, 컨테이너와 호스트에서 읽기 권한 확인. API/워커는 같은 호스트 UID를 쓰지만 전달 비밀과 DB 역할·mount 쓰기 권한은 분리. PostgreSQL의 최초 entrypoint만 공식 이미지의 초기화 권한 사용, DB 본 프로세스는 postgres 사용자. 비밀 파일 누락/DB 비밀번호 불일치는 재생성으로 덮어쓰지 않고 실패.

로컬 검증 명령: 저장소 루트에서 `python3 scripts/verify_containers.py`. Docker 엔진과 비root 계정 필요. 임의 프로젝트 이름·비공개 임시 폴더·loopback 임의 포트를 사용하고 기존 `.env.local`은 읽거나 수정하지 않음. `deploy/compose.yml`은 로컬 검증 구성. `Caddyfile.public`은 도메인 확보 후 검증할 초안이며 공개 포트/인증서 설정은 아직 운영 완료 범위 아님.

워커 Python 3.14 의존성은 `deploy/requirements.lock`에 직접·전이 패키지 버전과 Linux amd64/arm64 wheel 해시 고정, `pip --require-hashes --only-binary` 사용. SWMM은 EPA 고정 commit tarball SHA256 확인 후 빌드, 워커당 단일 작업에 맞춰 OpenMP 비활성화. 베이스 이미지 digest·Python wheel·Maven/pnpm 버전은 고정하되 빌드 단계 Debian 도구 패키지까지 비트 단위 재현을 보장하지는 않음.

초기 확인: 보안/가입/컨테이너 정책 Java 시험 8건, 파일 비밀 Python 시험 4건, Compose 문법 검사 통과. macOS Docker 엔진 연결 실패로 실제 컨테이너 검증은 아직 미완료. CI에 Linux amd64/arm64 독립 실행을 추가하여 결과 확인 예정. 아래 완료 증거는 실행 성공 후 갱신.

## HTTPS와 웹 응답

정적 앱과 `/api`는 동일 출처. API로 전달하는 Forwarded/X-Forwarded-*는 프록시에서 덮어쓰고 API에 직접 외부 접근 불가. 운영 세션은 `__Host-waterleague; Secure; HttpOnly; SameSite=Lax; Path=/`, Domain 미설정. HTTPS·CSRF·본문 한도·오류 비노출·CSP·HSTS 확인. 원격 도메인/인증서 확인 전 공개 바인딩 금지.

로컬 HTTPS 검증의 CA는 시험 폴더에만 보존, 시스템/브라우저 신뢰 저장소 변경 금지. 검증 클라이언트가 지정 CA를 신뢰하여 TLS·호스트명 검증 수행, `--insecure`/인증서 검증 비활성화 금지. 정적 경로 fallback과 API 오류 응답 분리, 누락된 JS/CSS는 HTML 성공으로 반환하지 않음. HTML 재검증·해시 자산 장기 캐시, 민감 API 응답 캐시 금지.

## 완료 증거

1. 이미지 빌드·고정 의존성·비밀 미포함·프로세스 UID/루트/볼륨 권한 검사.
2. 새 독립 DB에서 실제 마이그레이션, API/워커 자격으로 허용/금지 SQL 실행 검사.
3. 로컬 HTTPS 정적 앱·CSRF/가입/로그인·Secure 세션·설계 저장·실제 SWMM 워커·결과/ZIP 수치 재현 확인.
4. DB·API 외부 포트 비게시·워커 외부 접근 차단·재시작 후 데이터 보존·산출물 읽기 전용 확인.
5. 시험 생성 리소스/비밀/볼륨만 정리, 기존 개발 서버/DB/자료 보존.
6. Oracle에서는 OS/ARM64·디스크·TLS·메일·기관 인증·보존정책·오프사이트 암호화 백업/키 복구·동시 1~2워커 실측을 추가 검증. 로컬/CI 성공만으로 공개 운영 승인 금지.

근거: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), [Spring 외부 설정](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Caddy 프록시](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy), [PostgreSQL 공식 이미지](https://hub.docker.com/_/postgres).
