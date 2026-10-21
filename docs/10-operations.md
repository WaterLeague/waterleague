# 로컬·컨테이너·운영 계약

기준일: 2026-10-22. 아래 운영 조건은 공개 배포 검증이며 공개자료 기반 기능 구현의 선결 조건이 아니다. 진행 중인 로컬 API·워커·프론트는 사용자가 중지를 요청하거나 재시작이 필요한 변경이 아니면 유지한다.

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

기상청 계산 입력은 같은 HTTPS GET에 최대 2회만 시도한다. 통신 시간 초과·연결 중단과 HTTP 408/429/500/502/503/504에 한해 0.5~1초 분산 대기 후 재시도하며, `Retry-After`가 있으면 초 또는 HTTP 날짜를 해석한다. 2초보다 긴 대기나 잘못된 지시는 해당 수집을 실패 처리하고 요청 내부에서 조기 재호출하지 않는다. 인증·인증서·리다이렉트·기타 HTTP 오류, 과대/비밀값 포함 응답은 재시도하지 않는다. 응답 제한 4MB·TLS 검증·고정 주소를 유지한다. 요청별 30초 제한은 소켓 작업의 제한이며 전체 작업 실행시간을 보장하는 값이 아니다. 주간 수집의 매 요청/재시도 전에 임대를 확인하고 잃으면 다음 조회를 중단한다. AWS 구간 축소로 성공한 크기는 남은 수집에도 유지하며 호출 제한·대기 지시를 구간 분할로 우회하지 않는다. 별도 주간 작업의 실패 후 재선정은 기존 5분 간격을 따른다. HTTP 재시도는 조회 성공 원문만 정규화·겹친 관측 검사·재현 보관에 전달하며 과거 응답 캐시나 결측 대체를 수행하지 않는다. 근거: [Python urllib 요청·timeout](https://docs.python.org/3.12/library/urllib.request.html), [HTTP Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after).

API 오류·지연, 큐 길이·대기·실행, 품질 거부, DB·디스크·인증·export 감사 모니터링. 생존·준비 체크 분리·민감정보 차단.

주간 최초 계산의 선행 7일 강우는 기상청 조회·정규화 이후 남은 결측 분만 고정 서울시 관측으로 보강한다. 이 보강은 위 HTTP 재시도와 별도이며 현재 날씨·설치 이후 점수 구간에는 적용하지 않는다. 서울시 공식 HTTPS 다운로드는 별도 키 없이 조회하고 소켓 작업 시간 초과 25초·응답 8MB·50,000행 상한, 정확한 지점·10분 시간축·유한 비음수·중복 검사를 적용한다. 보조 관측도 부족하면 기존 실패·재시도 경로를 따른다. 원문·고정 지점·거리·보강 분·평균 분배 가정을 보관하며 기존 성공 계산의 선행 입력은 유지한다. [자료 계약](14-seoul-observations.md#주간-선행-강우-결측-보강) 참조.

DB·모델·출처·결과 백업, 암호화·키 분리·복원 훈련. 복원 뒤 관계·해시·랭킹 재계산 확인. RPO/RTO와 단일 서버 장애 시 제출·마감 정책은 운영 전 정의.

배포 전 의존성·secret·권한·migration·backup·ARM64 SWMM·수치 회귀·성능 확인. 모델 변경과 코드 배포 분리, 진행 리그 입력 자동 덮어쓰기 금지. 이전 이미지 복귀와 DB 호환성 검증.

운영 이미지 빌드 전과 워커 이미지 내부에서 `scripts/build_score_policy.py --check`를 실행한다. 계산/순위 코드와 고정 정책이 다르면 게시·배포를 중단한다. 주간 계산의 코드 정책 갱신은 보관된 이전 정책·입력·결과 해시, 동일한 지표/정밀도/시간 규칙과 실행 환경을 확인한 뒤 설치 이후 전체 관측을 재생한다. 기존 모든 분의 기준/설치 상태·기여량 및 주별 적립값이 완전히 일치한 경우에만 새 결과와 정책 식별자를 같은 트랜잭션으로 게시한다. 이전 성공 작업과 원문은 보존하고 새 요청에 이전 정책 조건을 연결한다. 수치 또는 실행 조건이 달라지면 자동 이관을 거부한다. 기존 정책의 점수가 있는 시설부터 재생하되 실행 중 중복 임대와 실패 후 5분 대기는 유지한다. 서로 다른 정책 결과가 남아 있는 동안 주간 전체 순위 비교는 기존대로 보류한다.

실행 가능한 로컬 검증 구성과 Linux amd64/arm64 증거는 이 문서의 컨테이너·HTTPS 계약 참조. `python3 scripts/verify_containers.py`는 별도 프로젝트·임의 loopback 포트·임시 비밀로 전체 HTTPS 계산을 검사 후 정리하며 기존 `.env.local`·개발 DB를 읽지 않음. Oracle 예산 표는 제안이고, CI Compose의 보수적 한도(API 2GB·DB 2GB·워커 2GB)를 운영 실측 결과로 해석하지 않음.

## 대회 배포 상태 · 2026-10-21

V33은 대회·참가·재해 제출 연결·실시간 점수의 4개 테이블을 추가한다. 현재 로컬 API에 적용했고 API/워커 갱신, 격리 PostgreSQL의 대회·관리자 결과 시험과 기존 주간/재해 회귀를 통과했다. 새 계산 큐는 없으며 실시간 대회 점수를 기존 주간 결과와 같은 트랜잭션에서 게시한다. 정책이 바뀌는 코드 배포는 API/워커의 정책 해시 일치를 확인한다.

2026-10-22 운영 배포 작업에서 V33 테이블을 명시적 권한 목록에 추가했다. API는 대회·참가·제출을 관리하고 계산 점수는 조회만 허용한다. 워커는 대회 조건·참가와 회원의 id/enabled/approval_status, 기관의 id/approved 열만 조회하며 계산 점수 열만 갱신한다. 회원 비밀번호·MFA·신청 원문 접근은 허용하지 않는다. V34 알림 큐는 API만 접근한다.

배포 순서는 백업 → V33 마이그레이션 → 역할 권한 적용/검사 → 같은 정책의 API·워커 기동이다. 백업·복원 대상에 4개 대회 테이블과 참조하는 기존 설치/작업/재해 제출·산출물을 함께 포함한다. 주최 조직·참가 시각·고정 규칙/정책·조건별 점수·미완료 계산을 보존하고 복원으로 마감 기간이나 소유권을 변경하지 않는다.

Caddy의 SPA fallback은 페이지별 주소와 상세 페이지의 새로고침을 처리하고 API는 별도 경로로 전달한다. 관리자·대회 비공개 결과의 `no-store`를 정적 파일 캐시 규칙으로 덮어쓰지 않는다. 새 페이지의 직접 브라우저 조작은 로컬 브라우저 제어 비활성화로 미검증이며 HTTP/자동 시험과 구분한다.

```sh
simulation/.venv/bin/python scripts/verify_league_postgres.py --suite competitions
```

검증 건수·해당 코드 시점은 [검증 이력](12-validation-log.md#2026-10-21-게임-대회관리자-결과페이지-경로-정리)에 둔다.

## CI 재현 환경 · 과거 검증 이력

아래 대규모 검증 CI는 2026-10-22 사용자 요청으로 제거했다. 재현 도구와 시험 코드는 로컬에서 유지하며 현재 main은 이 문서 하단의 운영 배포 workflow를 사용한다.

`main`, `dev`, `feat/**`, `fix/**` 푸시와 PR에서 `.github/workflows/verify.yml` 실행. 프론트 포맷·추적 중인 단위 시험·빌드·의존성 감사, PostgreSQL API 회귀, 큐·검색·복원, Linux amd64/arm64 HTTPS 컨테이너 계산을 검사한다.

백엔드 통합 시험은 운영과 같은 PostgreSQL에서 SQL 마이그레이션·부분 인덱스·제약을 검사한다. H2 대체 실행은 사용하지 않는다. `PostgresIntegrationTest`는 loopback의 전용 시험 DB 이름만 허용하고 전체 백엔드 회귀에서는 클래스 사이의 계정·작업·세션을 초기화한다. 여러 JVM·워커가 준비 자료를 이어 쓰는 개별 suite는 `preserve-fixtures` 시험 옵션으로 보존한다. 재시작 지속성 시험은 이전 JVM의 시험 자료를 보존한다. 운영 마이그레이션 원문과 기존 로컬 DB는 변경하지 않는다.

```sh
simulation/.venv/bin/python scripts/verify_league_postgres.py --suite backend
```

수치 회귀는 `simulation/uv.lock`과 `uv sync --locked --extra flood`로 ANUGA·공간 의존성을 준비한다. 비상업용 Triangle·meshpy 제외 정책을 유지한다. `build_ci_engines.py`로 고정 EPA 원본의 13개 엔진 변형을 빌드한 뒤 `test_simulation.py`가 모든 시험 모듈을 4개 작업에 중복 없이 분배한다. 각 모듈을 별도 프로세스에서 실행해 EPA·ANUGA 네이티브 런타임의 교차 적재를 방지한다. 시험 제외나 오류 무시로 통과시키지 않는다. [uv 잠금·동기화 공식 문서](https://docs.astral.sh/uv/concepts/projects/sync/).

`prepare_ci_sources.py`는 `simulation/tests/fixtures/public-sources-v1.json`의 원본 SHA-256·크기·경로를 검사한 공개 자료만 복원한다. 기상청 관측, Mendeley 공개 연구 모형(CC BY 4.0), 비용 근거 논문(CC BY-NC 3.0), EPA 공개 교육 사례의 출처와 이용 조건을 원문별로 보존한다. 이 자료의 이용 조건은 코드 라이선스와 별도이며 논문 원문은 비상업적 재현 시험용이다. 기본/재해 관측과 관측소 좌표, 재해 3사건·25개 구의 선행 7일 및 지표 연구의 14/28일 기상, 고정 EPA ZIP을 포함한 1,745개 원문을 제공한다. 모든 보관 기상 요청의 포함 여부와 원형 공간의 100개 관측 결속을 검사한다. EPA 참조 검증은 이 고정 원본을 사용해 CI에서 외부 다운로드에 의존하지 않으며 TLS 검증을 우회하지 않는다. 비밀키·개인자료는 묶음에 포함하지 않는다. 기존 파일이 다르거나 링크 경로이면 덮어쓰지 않고 실패한다.

큐 suite는 `test_worker_queue.py`만 실행한다. 재해·회원 설계 등 별도 준비 데이터가 필요한 suite는 해당 준비 흐름에서 실행한다. 프론트 포맷 검사는 생성된 `qa/*.local.json`을 제외하고 추적 중인 소스·시험 입력은 계속 검사한다.

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

원형 공간 자료는 계산 결과 캐시와 별도다. API/워커 이미지에 포함한 `native-play/v1`의 공개 압축 115파일 449,886,848바이트를 고정 매니페스트·조각별 압축/원문·전체 DB 해시로 확인해 복원한다. DB는 3,829,805,056바이트이며 결과 캐시의 2GiB/7일 삭제 정책에 포함하지 않는다. Compose는 같은 호스트 상태의 `cache/native-spatial`을 `NATIVE_SPATIAL_CACHE`로 공유하고 계산 결과는 `cache/results`를 사용한다. 버전 디렉터리 0700·DB 0400·Java/Python 공통 POSIX 잠금·임시 파일 동기화/원자적 게시를 적용한다. 손상된 기존 파일은 덮어쓰지 않고 시작/조회 오류로 보존한다. 비웹 마이그레이션은 이 DB를 복원하지 않는다. 별도 원자료 폴더나 외부 저장소 접속 없이 이미지의 공개 묶음으로 복원한다.

API의 SQLite 네이티브 라이브러리는 이미지 빌드에서 해당 아키텍처용으로 추출한다. 읽기 전용 루트·`/tmp` noexec를 유지하며 JNI 경로를 고정한다. [SQLite JDBC 3.53.4.0](https://github.com/xerial/sqlite-jdbc/releases/tag/3.53.4.0)·[JTS 1.20.0](https://github.com/locationtech/jts/releases/tag/1.20.0)을 고정하고 Java 25·Linux ARM64에서 조회를 검증한다.


## 리그 참가 PostgreSQL 통합 검사

`simulation/.venv/bin/python scripts/verify_league_postgres.py`는 `.env.local`을 값 출력 없이 읽고 로컬 PostgreSQL에 UUID 이름의 독립 시험 DB를 생성. Java 25의 실제 HTTP·MFA·CSRF·트랜잭션 시험 후 성공/실패와 관계없이 자신이 생성한 DB를 삭제. 로컬 시험 계정의 CREATEDB 권한 필요; 운영 서비스 계정에 해당 권한을 부여하는 배포 지침이 아님. 원본 계산·공개 제출·리그 수 변화 검사, 0600 로그 경로와 통과 여부만 출력. 과학 모델 검증이나 기존 원본 DB의 쓰기 시험이 아님.

기존 검증 CI는 별도 PostgreSQL 18.4 서비스 DB에서 같은 참가 통합 검사를 실행했다. CI의 공개 시험용 비밀번호는 서비스 컨테이너 전용이며 로컬·운영 비밀과 분리. 실제 Oracle 처리량·자원 제한은 별도 검증.

## 컨테이너 배포·로컬 HTTPS 검증 계약

2026-10-17. 문서 07·10의 비밀 분리·권한·복원 기준을 실행 가능한 배포 구성으로 연결. Linux amd64/arm64 CI의 전체 검증 통과, 당시 Oracle 접속/도메인은 사용자 확인 대기였으며 2026-10-22의 실제 운영 결과는 아래에 기록한다. CI 검증을 실제 Oracle 배포·부하·외부 백업 완료로 표시하지 않음. 모델은 기존 EXPLORATORY 유지.

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

로컬 검증 명령: 저장소 루트에서 `python3 scripts/verify_containers.py`. Docker 엔진과 비root 계정 필요. 임의 프로젝트 이름·비공개 임시 폴더·loopback 임의 포트를 사용하고 기존 `.env.local`은 읽거나 수정하지 않음. `deploy/compose.yml`은 로컬 검증 구성. `Caddyfile.public`의 실제 공개 포트/인증서 검증은 아래 Oracle 운영 배포 기록에 해당한다.

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


실행 이력: 2026-10-17 Linux amd64/arm64 컨테이너 검증은 [검증 기록](12-validation-log.md)에 보존한다. 당시 성공은 현재 Oracle VM·도메인·성능 검증을 대신하지 않는다.

## Oracle 운영 배포 · 2026-10-22

사용자 요청으로 `168.107.61.81`의 Ubuntu 24.04 ARM64·24GB 인스턴스에 배포하며, 도메인은 `waterleague.cloud`다. 가비아 A 레코드는 `@ → 168.107.61.81`, TTL 600이다. 공개 운영 요청이 과거 문서의 도메인/승인 대기 상태를 대체한다. 메일 인증·외부 백업 완료를 구현 완료로 간주하지 않는다.

`www.waterleague.cloud`는 가비아 CNAME `www → waterleague.cloud.`(TTL 600)으로 같은 서버에 연결한다. Caddy가 두 호스트의 공인 인증서를 각각 관리하고, `www` 요청은 경로·쿼리를 보존한 HTTP 308로 `https://waterleague.cloud`에 전달한다. 앱·로그인 세션의 기준 출처는 기본 도메인으로 유지한다. DNS 등록과 별도로 실제 HTTPS 인증서·리디렉션을 확인한다.

`.github/workflows/deploy.yml`은 main push와 main 수동 실행만 처리한다. 기존 대규모 테스트 check workflow는 사용자 요청으로 제거하고 로컬 검증 도구/시험 코드는 유지한다. CI는 SHA 고정 checkout, 읽기 전용 저장소 권한, 이미지 게시 권한, 직렬 배포를 사용한다. ARM64 API·워커·웹 이미지를 GitHub Container Registry에 커밋별로 게시하고 원격 호스트는 digest로 받는다. 오류 시 빌드·배포 단계가 실패한다.

### GitHub Actions Secrets

| 이름 | 용도 | 관리 |
| --- | --- | --- |
| `OCI_HOST` | 168.107.61.81 | 배포 대상 고정 |
| `OCI_USER` | ubuntu | SSH 계정 |
| `OCI_SSH_KEY` | 제공된 SSH 개인키 | Secret stdin 등록 |
| `OCI_SSH_PASSWORD` | 현재 SSH의 키 인증 뒤 추가 비밀번호 | SSH_ASKPASS로만 전달 |
| `OCI_KNOWN_HOSTS` | 접속 확인한 호스트 공개키 | StrictHostKeyChecking 필수 |
| `ADMIN_USERNAME` | 관리자 로그인 아이디 | 소문자·숫자·밑줄 4~32자 |
| `ADMIN_PASSWORD` | 관리자 비밀번호 | 8~128자, 사용자 설정 |
| `DISCORD_WEBHOOK_URL` | 운영 Discord 알림 목적지 | HTTPS discord.com 웹훅만 허용 |
| `KMA_API_KEY` | 주간 관측 수집 | 확보한 키 재사용 |

관리자 로그인은 이메일이 아닌 아이디다. 기존 관리자 기능(회원 승인·정지·복구, 대회·주간·재해 결과 조회)을 단일 ADMIN에 연결한다. 최초 배포의 비웹 일회성 `bootstrap-admin` 프로필이 관리자 계정을 생성하며 첫 로그인에서 본인이 TOTP 인증 앱을 등록한다. OTP는 ADMIN 전용이며 나머지 회원 유형에는 요구하지 않는다. 공개 가입으로 ADMIN을 만들 수 없다. 재배포는 같은 아이디만 허용하며 비밀번호 Secret 변경 시 Argon2id 해시를 교체하고 기존 세션을 폐기한다. MFA는 재설정하지 않는다. 다른 아이디/기존 일반회원과 충돌하면 실패한다. 초기화 후 서버의 관리자 평문 비밀번호 파일은 삭제한다.

DB 역할 비밀번호와 MFA 암호화키는 서버에서 최초 1회 생성해 `/opt/waterleague/state/secrets`의 0600 파일에 유지한다. 일부 파일만 유실되면 자동 교체하지 않고 실패한다. 공개 Compose는 API·워커에 필요한 Secret만 마운트하고 DB/API 포트는 게시하지 않는다. Caddy는 80→8080, 443→8443으로 자동 HTTPS를 처리한다. 실시간 기상 수집을 위해 운영 워커에는 외부 통신 네트워크를 연결하며 고정 기상청 HTTPS 요청 검증은 유지한다. 로컬 격리 검증 Compose의 워커 외부 통신 차단과 구분한다.

`deploy/ci.py`가 일회성 비공개 묶음을 SSH로 전달하고 `deploy/receive.py`가 파일 종류·경로·크기를 검증한다. `deploy/apply.py`는 호스트 잠금, digest 이미지 다운로드, 기존 API/워커 정지, 암호화 백업, 역할 초기화, Flyway, 최소 권한 적용, 관리자 초기화, 서비스 준비 상태, 실제 인증서 HTTPS를 차례로 확인한다. GitHub 임시 레지스트리 토큰과 전송 묶음은 사용 후 삭제한다. 배포 실패 시 이전 릴리스의 이미지로 복귀하며 DB를 자동 역마이그레이션하지 않는다. 이번 V34는 추가 스키마이며 이전 API와 공존 가능하다. 향후 파괴적 스키마 변경에는 별도 호환 단계가 필요하다.

기존 운영 데이터는 배포마다 DB 논리 덤프·재현 산출물·비밀/고정 릴리스를 age로 암호화하여 `/opt/waterleague/backups`에 최근 7개 보관한다. 복호화 키는 별도 `/opt/waterleague/backup-identity.age`에 0600으로 저장한다. 이는 동일 서버의 배포 복구 수단이며 서버 자체 유실에 대비한 오프사이트 백업을 의미하지 않는다. 최초 배포의 빈 DB에는 기존 데이터 백업이 없다.

### Discord 운영 알림

V34 DB 트리거가 신규 MEMBER 가입, 주간 신규 설치, 재해 최종 제출을 `notification_outbox`에 같은 트랜잭션으로 기록한다. 롤백 시 알림도 취소하고 event_type/source_id 유일 제약으로 같은 활동의 재요청을 중복 기록하지 않는다. 관리자 초기화와 단순 실험은 알림 대상이 아니다. 사용자 ID·아이디·닉네임·회원 유형·소속/설치 구 코드와 활동 요약만 전달하며 비밀번호·세션·OTP·신청 목적 원문은 제외한다.

API의 별도 스케줄러가 한 번에 한 건을 임대해 전송한다. Discord `wait=true`의 성공 응답 후 완료 처리, 전체 멘션 차단, TLS 검증, 리디렉션 차단, 연결 5초/요청 10초 제한을 적용한다. HTTP 408/429/5xx 및 통신 실패는 최대 8회 재시도하고 429의 Retry-After 동안 발송을 멈춘다. 전달 완료 후 DB 기록 전 장애 시 재발송될 수 있어 수신 측 기록 ID로 식별한다. 전송 완료 기록은 7일, 나머지 기록은 최대 30일 보관한다. 웹훅 URL·응답 본문·전송 사용자 정보는 일반 로그에 출력하지 않는다. 웹훅 미설정 로컬 환경은 발송하지 않는다.

근거: [GitHub Actions 보안](https://docs.github.com/en/actions/reference/security/secure-use), [Discord webhook](https://docs.discord.com/developers/resources/webhook), [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https), [Docker Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/).

### 첫 운영 배포 확인

2026-10-22 KST, 커밋 `45b31eeaa69d433357d1747accf61ad3e704631a`의 [GitHub Actions 실행](https://github.com/WaterLeague/waterleague/actions/runs/39626445638)이 성공했다. `https://waterleague.cloud`의 공인 인증서 검증·HTTP→HTTPS 전환·실제 첫 화면/주간 지도 로드·API 상태 UP을 확인했다. API·DB·웹의 준비 상태와 워커 실행, V34 적용, 활성 ADMIN 1개·일반회원 0개, 초기화 비밀번호 파일 삭제를 확인했다. 관리자 첫 로그인 시 본인의 인증 앱 등록이 필요하다.

Discord 웹훅 메타데이터 조회는 HTTP 200이며 일반 로그의 비밀값 미노출을 검사했다. 세 활동의 알림 생성·중복/롤백 처리는 독립 DB 시험으로 확인했고, 운영 DB에 검증용 가입·시설·재해 제출을 생성하지 않았다. 실제 사용자 활동의 Discord 수신은 아직 발생 전이다. 공개 HTTPS의 CSRF 세션 속성과 비인증 관리자 API 401, 비밀 경로 404도 확인했다. 문서만 갱신하는 완료 기록 커밋에는 `[skip ci]`를 사용해 동일 앱의 불필요한 재배포를 생략한다.

V35 적용 시 비관리자의 사용하지 않는 OTP 등록 기록을 제거한다. 관리자 MFA는 보존하며 조직 계정은 승인 후 비밀번호로 로그인한다. 이전 V34 이미지로 복귀하면 조직 계정이 OTP를 다시 요구할 수 있으므로 복귀 후 인증 정책을 확인한다.

2026-10-22 KST, `6e617cb8213b1372494943ad201ae2245cf0598e`의 [운영 배포 실행 39629260140](https://github.com/WaterLeague/waterleague/actions/runs/39629260140) 성공. 운영 V35·비관리자 OTP 기록 0건·활성 ADMIN 1개와 실제 도메인의 OTP 없는 기본 로그인 화면 확인. HTTPS·공개 API·비인증 관리자 차단·CSRF 세션 검사 통과. 배포 전 age 백업의 복호화와 DB 덤프/산출물/비밀/릴리스 포함 검사를 통과했으며, 동일 서버 백업이고 별도 DB 복원 훈련은 아니다. 운영에서 발생한 회원가입 알림 2건은 Discord 전송 완료·실패 0건으로 확인했다. 검증용 회원가입이나 활동 기록은 만들지 않았다.

2026-10-22 사용자 요청의 운영 더미 계정은 `TEST_` 아이디로 식별하며 닉네임은 소속 구와 무작위 별칭을 조합한다. 23개 구에 각 3계정·계정별 3시설을 생성하고 중구(11140)·강북구(11305)는 비워둔다. 10계정은 2022년 호우를 실제 계산·제출한다. 운영용 계정은 비공개 일괄 생성으로만 만들며 공개 가입의 소문자 규칙은 유지한다. 로그인은 기존 소문자 아이디와 `TEST_[a-z0-9_]{1,27}`을 허용한다. 사용자 활동을 모방하는 가상 관측·효과·점수를 넣지 않고 설치 시각·기상·계산·순위를 원래 서비스 경로에서 생성한다. 계정 자격·운영 활동의 개인별 식별자는 비공개 실행 기록으로 보관한다.

## 2026-10-22 운영 TEST 계정·시설·재해 제출 실행

- `TEST_20261022_<구코드>_<01~03>` 형식의 계정·TEST 닉네임 69개 생성. 23개 구마다 3명, 계정당 3개·총 207개 시설 설치. 중구(11140)·강북구(11305)의 계정 배정·설치 제외 및 공개 API의 해당 구 설치 0개 확인. 기존 이용자의 계정·설치 변경 없음.
- 운영 이미지 `7049528045b1fc9151123e128dab8bf8bc7ba439`의 [배포 실행 39632117254](https://github.com/WaterLeague/waterleague/actions/runs/39632117254) 성공. TEST 로그인 HTTP 확인, 공개 가입 TEST 아이디 거부·소문자 가입 유지의 독립 PostgreSQL 4검사, 프론트 로그인 검사·프로덕션 빌드 통과.
- `deploy/SeedTestPlayers.java`를 비웹·최소 API DB 역할의 일회성 컨테이너에서 실행. 동일 계정·부지·요청 키의 재사용과 배치/역할/소속 검증을 적용하고 기존 설치·예산·저장 설계·계산·최종 제출 서비스를 호출. 서버 설치 시각·공개 지도 조건·관측 입력·실제 SWMM 계산을 사용하며 점수·관측·순위 직접 입력 없음. 공개 HTTP의 대량 가입/로그인 제한을 해제하지 않음.
- 서로 다른 10개 구의 TEST 플레이어가 2022년 호우의 3시설 설계를 저장하고 설치 시각 이후 실험 10건·전체 사건 제출 10건 실행. 20건 모두 SUCCEEDED, 인증된 랭킹 API에 TEST 결과 10개·동일 비교 집단·보류 0건 확인. 양수/음수 결과를 그대로 보존.
- `deploy/ProcessTestQueue.py`는 기존 claim/process 임대·동시성·해시 검사를 사용한 유한 작업자. 임시 작업자 2개는 20건 완료 후 종료·컨테이너 제거 확인. 기존 주간 워커는 관측 계산을 순차 진행하며 207개 모두의 점수 완료로 표시하지 않음.
- 가입 69건·주간 설치 207건·재해 제출 10건의 Discord 알림 286건 전송 완료·실패 0건 확인. 개인별 자격과 실행 식별자·요청 원문은 로컬/서버 비공개 기록에만 보관, 저장소·이미지·보고서에 비밀번호/해시 미포함.

시설 신규 설치 Discord 알림은 설치자 정보와 함께 지도 후보의 식별 이름·설치 구 이름·공개 주소를 포함한다. 주소가 없는 후보는 `공개자료에 주소 없음`으로 표시한다. 위치 정보는 설치와 같은 트랜잭션에서 outbox에 고정하며 원문 주소를 추정하거나 웹훅에 비밀번호·세션을 보내지 않는다.

2026-10-22 후속 요청으로 위 69계정의 닉네임을 구 이름+무작위 별칭으로 변경했다. 아이디·비밀번호·소속·시설·제출은 유지했으며 변경 전 암호화 백업과 이전/새 닉네임의 비공개 실행 기록을 보관했다. 비공개 계정 목록도 같은 닉네임으로 갱신했다.
