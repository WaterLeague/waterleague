# WATER LEAGUE

서울 성수동 공개 건물 형상과 기상청 실제 분강우를 사용해 시설을 배치하고, EPA SWMM으로 계산·경쟁·연구 기록 공유를 수행하는 3D 웹 게임.

**현재 등급은 EXPLORATORY.** 실제 관측 강우와 공개 형상을 사용하지만, 배수경계·관망·표고·토양·현장 유출 검증이 없어 현실 침수나 공사 효과를 예측하는 단계가 아니다. 연구자는 입력·가정·계보·결과를 재현해 후보를 검토할 수 있다.

## 구현

- 94개 공개 건물 형상, 13개 실험 표면, 빗물정원·투수포장·녹화지붕 배치, 면적·원화 예산·되돌리기·불변 저장 버전.
- 기상청 서울 108·성동 421 관측소, 3개 날짜·4개 실측 분강우 모델. 공식 SWMM 5.2.4, 기준안 비교·물수지·투수계수 가정 범위·분 시계열.
- 실제 SWMM CPU 기준안·후보 원장과 고정 배치의 네 강우 비교, 개인 저장 버전의 다강우 일괄 계산·비교 그룹·배치 복사.
- 플레이어 즉시 가입, 기업·기관·정부 회원 가입 신청·단일 관리자 승인·반려·정지, Argon2id·DB 세션·CSRF·TOTP MFA·소유권 검증.
- PostgreSQL 작업 큐, 멱등 요청·전역 입장 잠금·lease·fencing·시간 제한, 서버 재계산 점수와 탐색 순위.
- 기관 리그 개설·초안 검토·공개·취소, 고정 예산·시설·제출 한도 적용, 실제 계산 제출·독립 순위·기관 연구 연결.
- 리그별 시설 개수·합산 면적 상한, 원화 상금·수상 예정 인원·심사 안내 공개 시 고정. 실제 지급 별도.
- 기관별 공유 동의·철회, 동의된 제출 버전까지의 이력·결과 열람, 재현 ZIP·감사 기록.
- 계산·목적별 사업 활용 요청과 명시적 동의·철회, 기관 검토 의견·조건 기록, 목적을 표시한 재현 ZIP.
- 비용은 원(KRW). 진주시 공개 사업계획 단가 참고, 서울·시점·규격 차이 미보정. 실제 사업비 견적과 구분.
- 브이월드 도로명주소 건물 실시간 대조, OSM 경계와 겹쳐 보기·지상 층수 확인. 저장·연구 입력 편입 없이 화면 대조에만 사용.

## 로컬 실행

JDK 25, Node 22.13 이상, pnpm 11.25.0, Python 3.12~3.14, uv, PostgreSQL, CMake·C 컴파일러 필요. macOS SWMM 빌드는 Homebrew libomp 사용.

`.env.example`은 빈 비밀값 템플릿이다. 기존 `.env.local`을 그대로 사용하고, 첫 설정에서만 예제를 복사한다. `.env`는 사용하지 않는다. DB 접속정보는 `DB_URL`, `DB_USER`, `DB_PASSWORD`, 워커는 `DATABASE_URL`; 외부 강우 재수집에만 `KMA_API_KEY` 필요. 공개된 파생 강우로 계산할 때는 기상청 키가 필요하지 않다.

건물 대조는 `VWORLD_API_KEY`, `VWORLD_DOMAIN`(등록 서비스 URL) 설정 후 API 재시작. `python3 scripts/probe_vworld.py`로 키를 노출하지 않고 연결 진단 가능. 로컬 실행기는 API·워커·프론트에 각각 필요한 비밀값만 전달한다. 층수는 실측 높이·지표고가 아니며, 대조 자료를 현장 검증이나 계산 입력으로 승격하지 않는다.

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

macOS 다중 JDK 환경: `export JAVA_HOME=$(/usr/libexec/java_home -v 25)`. 개발 DB 기본 포트 55432, API 8080, [웹 5173](http://127.0.0.1:5173/). Spring Flyway가 스키마 적용. 테스트는 임시 H2, 실제 로컬 실행은 PostgreSQL 사용. 기본 관리자·우회 계정 없음.

## 검증

```sh
./backend/mvnw -f backend/pom.xml verify
pnpm --dir frontend test
pnpm --dir frontend build
PYTHONPATH=simulation simulation/.venv/bin/python -m unittest discover -s simulation/tests -v
python3 scripts/verify_snapshot.py
python3 scripts/verify_model.py
# 내려받은 재현 묶음: 현재 설치된 동일 빌더와 엔진만 실행
simulation/.venv/bin/python scripts/verify_bundle.py /path/to/bundle.zip --rerun
```

## 문서

- [제품 요구사항](docs/01-product.md) · [연구 적합성](docs/02-scientific-validity.md) · [자료 계보](docs/03-data-provenance.md)
- [아키텍처](docs/04-architecture.md) · [데이터 모델](docs/05-data-model.md) · [API](docs/06-api.md)
- [보안](docs/07-security.md) · [3D·UX](docs/08-experience.md) · [작업 현황](docs/09-delivery.md)
- [운영](docs/10-operations.md) · [검증 기록](docs/11-validation-log.md) · [원화 비용](docs/decisions/0003-krw-cost-model.md)
- [백엔드](backend/README.md) · [프론트](frontend/README.md) · [계산 엔진](simulation/README.md) · [출처](data/README.md) · [Git 규칙](CONTRIBUTING.md)

공식 현장 평가·Oracle 공개 운영은 후속 검증 대상. 독립 현장 관측·설치 적합성·비용 검토·운영 인증과 백업 검증 없이 현재 모델을 공식 등급으로 승격하지 않는다. 로컬 논리 복원 훈련과 운영용 암호화·외부 보관 백업은 [운영 문서](docs/10-operations.md)에서 구분한다.
