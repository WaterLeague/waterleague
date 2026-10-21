# WATER LEAGUE

서울의 공개 지도와 관측 강우로 빗물관리 시설을 배치하고 효과를 비교하는 게임이다. 주간 서울 대항전·재해 모드·랭킹과 조직 회원이 개최하는 대회를 제공한다. 현재 일반 설치 시설은 7종이며, 결과는 명시한 가정 아래의 탐색 계산이다. 서울 전역 지도 제공이 서울 전역의 검증된 실시간 침수 예측을 뜻하지 않는다.

**제공 범위와 미지원 항목은 [완료 범위·제외 기준](docs/09-delivery.md)을 따른다.** 서울 25개 구 수치지형도로 지도·설치 후보·주간/재해 계산의 공간 참조를 통일했다. 일반 설치 7종의 예산·관측 계산·저장·제출·체적 차이 순위를 제공한다. 빗물이용조는 건물과 크기를 선택하면 지붕 집수부·건물 옆 탱크가 함께 설치되며 문헌 용량·참고비와 명시한 배수 가정으로 계산한다. 실제 제품/시공 검증·소형 통 제품·실제 연결 유역·전체 LCC·현장 관리 회복 예측은 제외한다.

## 문서 안내

| 필요한 내용 | 기준 문서 |
| --- | --- |
| 현재 게임 규칙·설치·예산·권한 | [제품](docs/01-product.md) · [화면·조작](docs/08-experience.md) |
| 완료 범위·미지원·제외 조건 | [제공 범위](docs/09-delivery.md) |
| 수치 의미·가정·검증 한계 | [연구 적합성](docs/02-scientific-validity.md) · [EPA 참조 검증](docs/20-epa-reference-validation.md) |
| 공개자료·추가 확보 여부 | [출처](docs/03-data-provenance.md) · [자료 현황](docs/13-data-access.md) · [공간자료 검사](docs/19-spatial-source-audit.md) |
| 현재 서울 1:1,000 수치자료의 레이어·속성·코드 | [데이터 설명서](docs/21-seoul-topography-data-dictionary.md) |
| 강우·수위 자료와 비교 | [강우 카탈로그](docs/11-rainfall-catalog.md) · [서울 관측](docs/14-seoul-observations.md) · [관망·수위](docs/15-sewer-observations.md) |
| 시스템·저장·API·보안 | [아키텍처](docs/04-architecture.md) · [데이터 모델](docs/05-data-model.md) · [API](docs/06-api.md) · [보안](docs/07-security.md) |
| 현재 대회·관리자 결과 | [제품](docs/01-product.md#대회--2026-10-21) · [API](docs/06-api.md#대회와-관리자-결과--2026-10-21) |
| 보존된 연구 서버·권한 계약 | [과거 연구 리그](docs/17-league-participation.md) · [분석·후보 탐색](docs/18-institution-analysis.md) · [활용 동의](docs/16-utilization-consent.md) |
| 실행·배포·검증 증거 | [운영](docs/10-operations.md) · [검증 이력](docs/12-validation-log.md) · [기여 규칙](CONTRIBUTING.md) |

현재 계약은 해당 기준 문서에만 적고 날짜별 시험 결과는 검증 이력에 남긴다. 과거 이력의 화면·정책을 현재 요구사항으로 읽지 않는다. 삭제·통합한 문서의 이전 내용은 Git 이력에서 확인할 수 있다.

## 구성

React 19·TypeScript·Vite·R3F/Three.js 프론트, Java 25·Spring Boot API, PostgreSQL 작업 큐/세션, Python의 고정 EPA SWMM·ANUGA 계산으로 구성한다. 세부 버전은 lockfile·빌드 설정이 기준이다. 승인된 조직 회원은 대회를 개최하고, 관리자는 주간 시즌·재해·대회 결과를 조회한다. 기관 리그·연구실의 미사용 프론트 코드는 제거했으며 이전 기록·동의·재현에 필요한 서버 경로와 원자료는 보존한다.

[프론트 실행](frontend/README.md) · [API 실행](backend/README.md) · [계산 워커](simulation/README.md) · [데이터 관리](data/README.md)

현재 페이지 주소는 `/weekly`, `/disaster`, `/rankings`, `/competitions`, `/data`이며 관리자는 `/admin/members`, `/admin/results`를 사용한다. 재해 사건과 대회 상세도 개별 주소를 갖는다. 직접 접근·새로고침·뒤로 가기 계약은 [화면 문서](docs/08-experience.md#페이지-주소)에 둔다.

## 로컬 실행

JDK 25, Node 22.13 이상, pnpm 11.25.0, Python 3.12~3.14, uv, PostgreSQL, CMake·C 컴파일러 필요. macOS SWMM 빌드는 Homebrew libomp 사용.

`.env.example`은 빈 비밀값 템플릿이다. 기존 `.env.local`을 그대로 사용하고, 첫 설정에서만 예제를 복사한다. `.env`는 사용하지 않는다. DB 접속정보는 `DB_URL`, `DB_USER`, `DB_PASSWORD`, 워커는 `DATABASE_URL`; 외부 강우 재수집에만 `KMA_API_KEY` 필요. 공개된 파생 강우로 계산할 때는 기상청 키가 필요하지 않다.

지도·설치 후보·과거 사건·건물 대조는 저장된 버전의 자료를 사용한다. 주간 기상청 관측과 서울시 현재 도시데이터는 서버에서 직접 조회하며, 관측 시각·유효기간·실패 상태를 구분한다. 인증키를 사용하는 외부 자료 수집은 수집·진단 도구에서 수행하고 키를 브라우저·계산 자식 프로세스에 전달하지 않는다. 건물 대조는 번들 JSON·SHA-256을 서버 시작 시 검사한다. 자료 갱신 후에도 이전 계산의 자료 버전은 보존한다.

```sh
# 저장소 루트, 새 환경에서만 로컬 설정 파일 준비
cp -n .env.example .env.local
chmod 600 .env.local
# .env.local에 실제 DB 접속정보 설정, DB 준비 후 실행
uv sync --project simulation --locked
bash scripts/build_swmm.sh
pnpm --dir frontend install --frozen-lockfile
# 각각 별도 터미널
python3 scripts/run_local.py api
python3 scripts/run_local.py worker
python3 scripts/run_local.py frontend
```

macOS 다중 JDK 환경: `export JAVA_HOME=$(/usr/libexec/java_home -v 25)`. 개발 DB 기본 포트 55432, API 8080, [웹 5173](http://127.0.0.1:5173/weekly). Spring Flyway가 스키마 적용. 통합 시험은 격리 PostgreSQL, 실제 로컬 실행도 PostgreSQL을 사용한다. 기본 관리자·우회 계정 없음.

## 검증

```sh
simulation/.venv/bin/python scripts/verify_league_postgres.py --suite backend
pnpm --dir frontend test
pnpm --dir frontend build
PYTHONPATH=simulation simulation/.venv/bin/python -m unittest discover -s simulation/tests -v
python3 scripts/verify_snapshot.py
python3 scripts/verify_model.py
# 내려받은 재현 묶음: 현재 설치된 동일 빌더와 엔진만 실행
simulation/.venv/bin/python scripts/verify_bundle.py /path/to/bundle.zip --rerun
```
