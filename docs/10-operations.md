# 로컬·컨테이너·운영 계약

기준일: 2026-10-20. 아래 운영 조건은 공개 배포 검증이며 공개자료 기반 기능 구현의 선결 조건이 아니다. 진행 중인 로컬 API·워커·프론트는 사용자가 중지를 요청하거나 재시작이 필요한 변경이 아니면 유지한다.

목표 Oracle 4 OCPU·24GB, ARM64 가능성 포함. WebGL은 사용자 브라우저, SWMM은 서버 CPU. 실제 OS·디스크·네트워크는 배포 전 확인.

| 구성 | 초기 예산 제안 |
| --- | --- |
| reverse proxy·정적 파일 | 약 512MB |
| Spring Boot | heap 4GB, 컨테이너 여유 별도 |
| PostgreSQL/PostGIS | 약 4GB |
| SWMM worker | 동시 1·약 3GB |
| OS·파일캐시·피크·백업 | 잔여 |

실측 보장 아님. PostgreSQL 큐로 Redis 초기 선택 사항. CPU·메모리·실행시간 측정 뒤 동시성 조정.

외부 HTTPS, DB·워커 내부망, SSH 제한·forwarded header 신뢰 경계. 개발 HTTP 쿠키는 local 전용, 운영 오설정 시작 거부. 모델·이미지 digest·실행 아키텍처 고정.

미션별 셀·강우기간·보고간격·timeout·결과크기 상한. 사용자 큐 제한·lease heartbeat·재시도·dead letter. 실패 결과를 점수 0으로 순위 반영 금지. 결과 캐시와 권한·동의 분리. 임시파일 정리 전 재현 산출물 영속·해시 검증.

API 오류·지연, 큐 길이·대기·실행, 품질 거부, DB·디스크·인증·export 감사 모니터링. 생존·준비 체크 분리·민감정보 차단.

DB·모델·출처·결과 백업, 암호화·키 분리·복원 훈련. 복원 뒤 관계·해시·랭킹 재계산 확인. RPO/RTO와 단일 서버 장애 시 제출·마감 정책은 운영 전 정의.

배포 전 의존성·secret·권한·migration·backup·ARM64 SWMM·수치 회귀·성능 확인. 모델 변경과 코드 배포 분리, 진행 리그 입력 자동 덮어쓰기 금지. 이전 이미지 복귀와 DB 호환성 검증.

실행 가능한 로컬 검증 구성과 Linux amd64/arm64 증거는 이 문서의 컨테이너·HTTPS 계약 참조. `python3 scripts/verify_containers.py`는 별도 프로젝트·임의 loopback 포트·임시 비밀로 전체 HTTPS 계산을 검사 후 정리하며 기존 `.env.local`·개발 DB를 읽지 않음. Oracle 예산 표는 제안이고, CI Compose의 보수적 한도(API 2GB·DB 2GB·워커 2GB)를 운영 실측 결과로 해석하지 않음.

## 로컬 복원 훈련 계약

`verify_database_restore.py`는 운영 복구 명령이 아닌 격리된 복원 검사. 원본 DB의 REPEATABLE READ 스냅샷을 `pg_dump --snapshot`과 공유하고 새 `waterleague_restore_<무작위값>` DB에만 복원. 원본 DB 변경·기존 DB 덮어쓰기 금지. 생성한 DB만 마지막에 제거, 정상 종료·검사 실패 모두 임시 덤프 제거. 덤프 디렉터리 700·파일 600, 비밀값은 명령 인자·보고서·로그에 출력하지 않음.

세션·요청 제한 데이터는 덤프에서 제외하여 복원 후 전체 재로그인. 나머지 public 테이블은 정렬된 행 원문의 건수·SHA-256를 스냅샷과 대조. 마이그레이션 성공, 완료 계산별 불변 버전/입력/모델 hash·원화 비용·점수·재현 파일 manifest를 검사하고 같은 자료가 복원 DB에서 참조되는지 확인.

연구 후보는 개인 작업과 분리된 `research-candidates/<후보 UUID>/<token>` 경로 검사. 모든 연구 그룹의 계보 원문 hash·설정·선택한 원본 ID/버전/입력/원화 비용/점수·후보 arm/ordinal/배치/비용을 DB와 대조하고 고정 모델로 Python 생성 규칙을 독립 재생. 성공 후보뿐 아니라 대기/실패 후보도 생성 계보와 연결 여부 확인. 철회된 그룹도 저장 무결성 검사는 수행하되 자료 접근 권한을 복구하거나 공개 보고서에 원문을 기록하지 않음. 현재 동의·기관 권한은 복원된 테이블 및 API 정책으로 유지.

스냅샷이 참조하는 완료 개인/후보 작업의 manifest와 18개 파일을 검사 후 임시 디렉터리의 별도 사본으로 복사. 복사본 hash를 확인하고 복원 DB는 이 사본만 참조해 동일 검사 수행. 원본 자료 디렉터리는 읽기만 수행, 실패/완료 시 임시 사본 제거. 디렉터리/파일 링크·누락/변조·중복 JSON 키·비유한 수치·다른 경로의 파일 대체 거부. 원격 저장장치 장애 복구·암호화·WAL/PITR와는 별도인 로컬 논리 DB/산출물 복사 훈련.

검증용 DB 생성 권한과 원본 DB major에 맞는 PostgreSQL 도구 필요. `PG_BIN`으로 도구 디렉터리 지정 가능. 별도 DB의 이름은 호출자가 지정할 수 없으며 작업자가 생성한 식별자와 일치할 때만 제거. 강제 종료 시 남을 수 있는 `waterleague_restore_` DB·임시 폴더는 보고서·로그의 식별자를 확인한 뒤 정리.

원격 호스트·지원하지 않는 연결 옵션 거부, 임시 저장공간 사전 확인. 보고서는 기존 파일을 덮어쓰지 않으며 실패/정리 필요 상태를 구분. 성공한 덤프도 훈련 종료 시 제거되므로 이 명령 자체를 백업 보관 수단으로 사용하지 않음.

```sh
# .env.local의 로컬 DATABASE_URL 사용, PATH에 도구가 없으면 PG_BIN 지정
PG_BIN=/Applications/Postgres.app/Contents/Versions/18/bin \
  simulation/.venv/bin/python scripts/verify_database_restore.py \
  --report tmp/restore-check-20261016.json
```

이 검사는 오프사이트 암호화 백업·WAL/PITR·MFA 암호화 키 복구·Oracle 성능 측정을 대체하지 않음. PostgreSQL의 논리 덤프는 한 DB만 포함하며 role·tablespace는 별도 관리. 운영용 백업은 실행 산출물·원본자료·고정 모델과 코드 버전을 포함한 암호화 사본 및 별도 키 보관 필요.

근거: [PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html). 임의 외부 덤프는 SQL 실행 위험으로 자동 복원하지 않음.

2026-10-17 확장 검증: 기존 로컬 자료의 28개 테이블·개인 계산 13개·234개 산출물, 격리 HTTP 시험의 실제 SWMM 원본 2개·연구 후보 2개·72개 산출물을 각각 별도 사본으로 복원. 연구 계보 독립 재생·후보/원본 연결 확인, 동의 철회 기록 보존. 후보 비용·계보 hash·원본 연결 훼손 거부, 실패 후보는 생성 연결 검사를 유지하고 완료 산출물 집계에서 제외. 파일 이동으로 원본 경로를 사용할 수 없어도 사본만으로 검증하는 단위 검사 포함. 로컬 훈련이며 외부 저장소 장애 복구의 증거는 아님.

```sh
# 원본 DB와 분리한 임시 DB에서 실제 HTTP·SWMM·철회·복원 시나리오 실행
simulation/.venv/bin/python scripts/verify_league_postgres.py --suite restore
```

CI의 복원 시나리오는 고정 Ubuntu 24.04에서 공식 PGDG 저장소의 `postgresql-client-18`·`libpq5` `18.6-1.pgdg24.04+2` 사용. 서버 서비스는 기존 PostgreSQL 18.4, 서버/덤프 도구 major 일치 검사. 로컬 Postgres.app 도구는 18.4. [공식 Ubuntu 저장소 설정](https://www.postgresql.org/download/linux/ubuntu/)과 서명된 저장소 사용, 버전 변경 시 같은 복원 시험 재수행.

## 계산 캐시 운영

`docs/04-architecture.md`의 비공개 전용 디렉터리·128개/2 GiB/7일 상한 적용. 캐시는 재계산 가능한 임시 자료, `data/runs`의 작업별 재현 산출물과 다른 볼륨 경로 사용. 캐시 삭제는 기존 작업·순위·동의·다운로드 권한을 바꾸지 않음. 비활성화/경로 변경은 워커 설정으로만 수행. 로컬 파일 잠금·원자적 게시 범위이며 NFS·다중 호스트 공유나 동시 미스 계산 병합은 지원하지 않음. 실제 Oracle에서 캐시 읽기/쓰기 시간·적중률·보관량·큐 지연 실측 필요.


## 리그 참가 PostgreSQL 통합 검사

`simulation/.venv/bin/python scripts/verify_league_postgres.py`는 `.env.local`을 값 출력 없이 읽고 로컬 PostgreSQL에 UUID 이름의 독립 시험 DB를 생성. Java 25의 실제 HTTP·MFA·CSRF·트랜잭션 시험 후 성공/실패와 관계없이 자신이 생성한 DB를 삭제. 로컬 시험 계정의 CREATEDB 권한 필요; 운영 서비스 계정에 해당 권한을 부여하는 배포 지침이 아님. 원본 계산·공개 제출·리그 수 변화 검사, 0600 로그 경로와 통과 여부만 출력. 과학 모델 검증이나 기존 원본 DB의 쓰기 시험이 아님.

CI도 별도 PostgreSQL 18.4 서비스 DB에서 같은 참가 통합 검사를 실행. CI의 공개 시험용 비밀번호는 서비스 컨테이너 전용이며 로컬·운영 비밀과 분리. 실제 Oracle 처리량·자원 제한은 별도 검증.

## 컨테이너 배포·로컬 HTTPS 검증 계약

2026-10-17. 문서 07·10의 비밀 분리·권한·복원 기준을 실행 가능한 배포 구성으로 연결. Linux amd64/arm64 CI의 전체 검증 통과, Oracle 접속/도메인은 사용자 확인 대기. CI 검증을 실제 Oracle 배포·부하·외부 백업 완료로 표시하지 않음. 모델은 기존 EXPLORATORY 유지.

### 구성과 권한

- 공식 이미지의 버전·다중 아키텍처 manifest digest 고정. Java 25 LTS, Node 24 LTS, 프로젝트가 지원하는 Python 3.14, PostgreSQL 18, Caddy 2 사용. amd64/arm64 빌드와 SWMM 수치 재현은 각각 실행 증거 필요.
- 프록시/정적 앱만 호스트 포트에 연결. 기본 검증 바인딩은 `127.0.0.1`, DB·API·워커는 포트 게시 금지. 프록시-API와 DB 네트워크 분리, 워커의 외부 네트워크 접근 제거.
- API·워커 비root·read-only 루트·capabilities 제거·no-new-privileges·프로세스/CPU/메모리 제한. 작업 산출물은 워커 쓰기·API 읽기 전용, 캐시는 워커 전용. 마이그레이션·볼륨 초기화는 일회성 별도 서비스.
- DB 소유/마이그레이션, API, 워커 자격 분리. API는 필요한 업무 테이블 DML, 워커는 두 큐의 claim/lease/result 열과 배치 읽기만 허용. 워커의 회원·비밀번호·MFA/동의·기관 변경, API/워커의 DDL·역할 생성 금지. 새 마이그레이션 후 명시적 권한 목록 재검사.
- DB 초기화와 마이그레이션은 실패 시 API/워커 시작 중단. 기존 DB/볼륨을 재초기화하거나 운영 자료를 시험 DB에 덮어쓰지 않음.

### 비밀과 이미지

기존 개발 `.env.local` 유지. 운영/시험 비밀은 별도 비공개 디렉터리의 파일로 생성하고 Compose secret mount로 서비스별 최소 전달. 이것은 새 개발 `.env` 파일이 아니며 실제 값·키는 Git/이미지/명령 인자에 포함하지 않음. 파일 기반 Compose secret은 호스트 파일의 암호화를 보장하지 않으므로 호스트 권한/디스크 암호화·외부 키 보관은 운영 게이트.

API는 Spring config tree, 워커는 `_FILE` 설정으로 DB 연결 비밀을 읽고 값 출력 금지. 개발 KMA/VWorld 키는 기본 이미지/실행에 포함하지 않음. 모델·원자료 수집과 고정 모델 계산 배포 분리. `.dockerignore`로 `.env*`, `.git`, 개인정보/원자료/계산 파일/로그/IDE 파일 제외, 필요한 공개 고정 모델·출처만 명시적으로 복사.

파일 기반 Compose secret의 uid/gid 옵션은 bind mount에서 적용되지 않을 수 있으므로 실행 사용자는 호스트의 비root UID/GID와 일치. 상태 폴더 0700·비밀 파일 0600, 컨테이너와 호스트에서 읽기 권한 확인. API/워커는 같은 호스트 UID를 쓰지만 전달 비밀과 DB 역할·mount 쓰기 권한은 분리. PostgreSQL의 최초 entrypoint만 공식 이미지의 초기화 권한 사용, DB 본 프로세스는 postgres 사용자. 비밀 파일 누락/DB 비밀번호 불일치는 재생성으로 덮어쓰지 않고 실패.

로컬 검증 명령: 저장소 루트에서 `python3 scripts/verify_containers.py`. Docker 엔진과 비root 계정 필요. 임의 프로젝트 이름·비공개 임시 폴더·loopback 임의 포트를 사용하고 기존 `.env.local`은 읽거나 수정하지 않음. `deploy/compose.yml`은 로컬 검증 구성. `Caddyfile.public`은 도메인 확보 후 검증할 초안이며 공개 포트/인증서 설정은 아직 운영 완료 범위 아님.

워커 Python 3.14 의존성은 `deploy/requirements.lock`에 직접·전이 패키지 버전과 Linux amd64/arm64 wheel 해시 고정, `pip --require-hashes --only-binary` 사용. SWMM은 EPA 고정 commit tarball SHA256 확인 후 기존 실행과 동일하게 OpenMP로 빌드, 컴파일러가 연결한 libgomp 사본과 `$ORIGIN` RPATH 보존. 모델의 `THREADS 1`과 워커당 단일 작업 유지. 베이스 이미지 digest·Python wheel·Maven/pnpm 버전은 고정하되 빌드 단계 OS 도구 패키지까지 비트 단위 재현을 보장하지는 않음.

Corretto 빌드 단계의 unzip으로 Maven Wrapper의 ZIP 형식과 저장소 SHA256 검증 유지. 런타임 이미지는 빌드 단계의 추가 패키지를 복사하지 않음.

프런트 빌드 단계는 저장소의 `frontend/`, `data/`, `simulation/tests/fixtures/` 상대 위치 유지. 타입 검사에서 참조하는 고정 공개 모델·CPU 기준 JSON·후보 생성 fixture만 allowlist에 추가, 런타임 정적 이미지에는 완성된 dist만 복사. Caddy는 전달한 Forwarded와 X-Forwarded-Port/Prefix를 제거하고 주소·프로토콜·호스트를 직접 지정.

비밀 경로 기본값은 `/run/secrets/`, 네이티브 격리 마이그레이션 시험에 한해 `WATERLEAGUE_SECRET_DIR`로 비공개 경로 지정 가능. 필수 config tree 부재 시 시작 실패 유지.

### HTTPS와 웹 응답

정적 앱과 `/api`는 동일 출처. API로 전달하는 Forwarded/X-Forwarded-*는 프록시에서 덮어쓰고 API에 직접 외부 접근 불가. 운영 세션은 `__Host-waterleague; Secure; HttpOnly; SameSite=Lax; Path=/`, Domain 미설정. HTTPS·CSRF·본문 한도·오류 비노출·CSP·HSTS 확인. 원격 도메인/인증서 확인 전 공개 바인딩 금지.

로컬 HTTPS 검증의 CA는 시험 폴더에만 보존, 시스템/브라우저 신뢰 저장소 변경 금지. 검증 클라이언트가 지정 CA를 신뢰하여 TLS·호스트명 검증 수행, `--insecure`/인증서 검증 비활성화 금지. 정적 경로 fallback과 API 오류 응답 분리, 누락된 JS/CSS는 HTML 성공으로 반환하지 않음. HTML 재검증·해시 자산 장기 캐시, 민감 API 응답 캐시 금지.

금지 경로 `/.env*`, `/.git*`, `/actuator*`, `/run/*`는 별도 `handle`의 404로 처리하여 SPA fallback과 배타적으로 분리. [Caddy 처리 순서](https://caddyserver.com/docs/caddyfile/directives/handle)에 따라 fallback 바깥의 늦은 `respond`에 의존하지 않음.

### 완료 증거

1. 이미지 빌드·고정 의존성·비밀 미포함·프로세스 UID/루트/볼륨 권한 검사.
2. 새 독립 DB에서 실제 마이그레이션, API/워커 자격으로 허용/금지 SQL 실행 검사.
3. 로컬 HTTPS 정적 앱·CSRF/가입/로그인·Secure 세션·설계 저장·실제 SWMM 워커·결과/ZIP 수치 재현 확인.
4. DB·API 외부 포트 비게시·워커 외부 접근 차단·재시작 후 데이터 보존·산출물 읽기 전용 확인.
5. 시험 생성 리소스/비밀/볼륨만 정리, 기존 개발 서버/DB/자료 보존.
6. Oracle에서는 OS/ARM64·디스크·TLS·메일·기관 인증·보존정책·오프사이트 암호화 백업/키 복구·동시 1~2워커 실측을 추가 검증. 로컬/CI 성공만으로 공개 운영 승인 금지.


실행 이력: 2026-10-17 Linux amd64/arm64 컨테이너 검증은 [검증 기록](11-validation-log.md)에 보존한다. 당시 성공은 현재 Oracle VM·도메인·성능 검증을 대신하지 않는다.
