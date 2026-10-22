# 시뮬레이션 워커

현재 일반 지도는 7종 시설의 주간/재해 계산을 사용하며 연결 관망·지표·이용조 연구 경로도 별도로 존재한다. 일반 시설 효과와 연결 유역 침수 지표를 구분한다. 1차 출시 범위와 후속 연구는 [제공 범위](../docs/01-product.md), 수치 계약은 [연구 적합성](../docs/02-scientific-validity.md)을 따른다.

일반 이용조는 기본 자연배수와 문헌 수요 기반 일정 인출을 별도 EPA 실행으로 비교한다. 지붕 235m²당 하루 201L의 면적 비례·균등 수요 가정, 가용 저류에 따른 공급·부족, 같은 선행/설치 경계를 `cistern.demandScenario`에 보존한다. 잠재 공급량은 관측 재이용량이나 순위 가산값이 아니다. 재현 묶음의 `cistern_demand.inp/rpt/out`, `cistern-demand-run.json`, 시나리오 원문/코드 해시로 실행을 대조한다.

공식 EPA SWMM 5.2.4 소스 커밋 고정 빌드, C API 실행과 PostgreSQL lease 큐. 사용자 입력은 서버가 검증한 시설 배치로 한정한다. 원본 INP·실행 경로·엔진 설정을 외부에서 받지 않는다.

```sh
# 저장소 루트
bash scripts/build_swmm.sh
uv sync --project simulation --locked
PYTHONPATH=simulation simulation/.venv/bin/python -m unittest discover -s simulation/tests -v
python3 scripts/run_local.py worker
```

`require_complete`는 시간대, 간격, 전체 구간, 관측소, 원본 ID, 품질코드, 비유한 값·음수·결측을 검증한다. 빈 관측을 무강우로 채우거나 누적기간을 임의로 재분배하지 않는다. 승인 품질코드는 각 제공기관 명세를 검토한 정책으로 전달해야 한다.

초기 성수 연구 예제는 기상청 108 관측소의 실제 2024-07-18 05:00~23:59 KST 자료 사용. 일 누적 차분 1,139분·109.7 mm, 15분/60분 누적 교차 검증. 별도 제공기관 QC 플래그 부재와 부지 대표성 미검증 기록.

해당 초기 연구 예제는 13개 표면의 독립 유출·LID 침투·저류 계산이다. 현재 전체 게임의 후보 수/지원 시설 수를 뜻하지 않는다. 실제 배수관망·지형·현장 토양 모델 부재로 탐색 등급 유지. 표면 유출+LID 배수+최종저류−초기저류를 기준안과 비교한다. 기저 침투·초기 수분·시설 제원은 가정이며 범위 계산은 신뢰구간이 아니다.

저장 설계/후보 작업 경로는 작업당 90초 제한, CPU 75초, 파일당 64 MiB, lease 180초·최대 3회 획득·fencing. 운영 시 컨테이너 메모리·프로세스·디스크 한도 추가 필수. 결과 디렉터리는 `data/runs/<job UUID>/<lease UUID>`에 입력·출력·빌더·manifest 보존. `.env.local`의 키와 DB 비밀번호는 자식 실행 환경에서 제거.

초기 연구 예제의 엔진 테스트는 API/CLI 물수지 일치, 반복 재현, 해당 3종 LID, 5초/10초 시간간격 민감도, 무강우 평가 거부를 확인한다. 현장 관측과의 독립 검증을 대체하지 않는다.

동일 조건의 성공 산출물은 `data/private/simulation-cache`에 최대 128개·2 GiB·7일 보관한다. 모델·배치·엔진·빌더·실행 정책·플랫폼이 일치하고 파일 해시를 통과한 경우에만 대상 작업의 새 산출물 경로에 복사한다. `request.json`·회원·메모·이력은 공유하지 않는다. `result.json.execution.mode`의 `REUSED`는 새로운 독립 검증이 아니다.

`.env.local`의 `SIMULATION_CACHE_PATH`는 비어 있는 전용 경로 사용, `SIMULATION_CACHE_ENABLED=false`로 비활성화. 캐시 삭제·손상·만료·잠금 경합은 재계산으로 처리한다. 계산 중에는 캐시 잠금을 보유하지 않아 동시 미스는 각각 실행할 수 있다. 워커 설정 변경 후 처리 중 작업이 없는 시점에 재시작. 캐시는 영구 재현 산출물 백업을 대신하지 않는다. 상세는 [계산 캐시 계약](../docs/04-architecture.md#동일-물리-입력-계산-캐시) 참조.

## 대회 결과 게시

실시간 대회는 `competition_scores.py`에서 기존 주간 작업의 원 누적 체적 프레임을 사용한다. 참가·개최 이후 설치한 허용 시설만 평가하고 종료 분에서 절단한 결과를 주간 점수 게시와 같은 DB 트랜잭션에 저장한다. 별도 계산 엔진·작업 큐는 추가하지 않는다. 재해 대회는 기존 전체 사건 제출의 계산 결과를 조건별로 조회한다. 정책 불일치·계산 대기·실패를 0점으로 바꾸지 않는다. 스키마 V33과 배포 역할 권한의 현재 상태는 [운영 계약](../docs/10-operations.md#대회-배포-상태--2026-10-21)을 따른다.

## 관망·지표 엔진

`engine/network.py`는 별도 EPA DYNWAVE 빌드, `engine/surface.py`는 고정 ANUGA 4.0.1 실행. 기존 LID 바이너리와 운영 큐를 교체하지 않는다. 관망·2D를 같은 프로세스에 직접 로드하면 각 휠의 OpenMP 런타임이 충돌할 수 있으므로 `EngineProcess`를 사용한다. 상태는 자식 프로세스 안에 유지하며 부모는 허용된 입력·시간 전진·결과만 요청한다. 자식에 DB/API 비밀 환경을 넘기지 않는다. 강우 소유 영역 중복·외곽 경계 누락·비유한 값·평가 종료 누락은 실패 처리.

```sh
simulation/.venv/bin/python scripts/build_network_swmm.py
# 실행 중인 워커 환경을 보존하는 별도 선택 환경
UV_PROJECT_ENVIRONMENT="$PWD/tmp/flood-venv" uv sync --project simulation --locked --extra flood
MPLBACKEND=Agg tmp/flood-venv/bin/python scripts/verify_flood_engines.py \
  --output data/runs/flood-engine-reference-new
```

참조 실행에는 이미 확보한 `tmp/epa-reference/applications.zip` 사용. `--source`로 같은 해시의 원본 위치 지정 가능. 출력 디렉터리는 새 경로 필수. 관망 INP/RPT/OUT·상태 프레임·경계 변경과 지표 입력/수심/유속/SWW·엔진/코드 해시 보존. 실패 수치 사례도 manifest에 포함한다. 양방향 교환·지표 침투/증발·공개 연구 관망 입력 경로는 구현했으나 공개 서초 연구 관망은 회원의 지도 설계·비동기 작업·결과 조회에 연결했다. 실제 서울 관망과 지표의 일치된 기준고·현장 침수 대조·주간/재해 예산·순위 통합은 남아 있다.

## 연결 시설의 지표 결합

`run_coupled`의 `connectedFacilityDesign`은 기존 연결 설계와 같은 형식이며 원 지표의 `evaluationMetrics`도 필수다. 원 입력·설계·파생 INP·시설 초기 상태와 각 프레임의 시설 상태를 보존한다. 별도 `coupled_facility_network` 빌드가 같은 관망에서 시설 관측·지표 교환·외부 출구 지표를 함께 계산한다. 기존 관망/시설 바이너리는 교체하지 않는다.

```sh
tmp/flood-venv/bin/python scripts/build_coupled_facility_swmm.py
# 기존 관망 관측기와의 결과 비교용 빌드
tmp/flood-venv/bin/python scripts/build_network_swmm.py --metrics
COUPLED_FACILITY_EVIDENCE_DIR=data/runs/coupled-facilities-new PYTHONPATH=simulation \
  tmp/flood-venv/bin/python -m unittest simulation.tests.test_coupled_facilities
```

시험 강우·집수·관망·지표는 수치 확인용 합성 입력이며 공개 현장 자료가 아니다. 생물저류·침투 트렌치·이용조의 연결, 이용조 배수 개방, 기존 관측기와의 이진 결과 일치, 표시 주기 독립성과 작은 식생수로의 시설 수지 실패 전파를 확인한다. `connectedFacilities`의 수지는 원 유출 계산 시각 기준으로 별도 표시하며 관망/지표 수지에 시설 배수·저류를 다시 더하지 않는다. 전체 유역 물수지·현장 효과·LID 배수 역압을 검증한 것으로 해석하지 않는다.

## 연결 시설의 선행 관측 초기화

`forcing/network_initialization.py`는 집수구역별 보관 AWS 강우와 FAO-56 기상을 원문에서 재검사하고 7/14/28일 초기화 입력을 생성한다. 관망은 전체 기간을 UTC로 선언해야 하며, 원 관망의 날짜·외부 유입·방류구 수위를 자동 연장하지 않는다. 외부 시계열은 기간·간격 근거가 필수다. 관망 형상·재료·침투 회복 곡선·증발 제어를 보존하고 강우계·잠재 증발률만 연결한다.

`engine/initialized_facilities.py`는 선행→평가를 한 번의 시설/관망 실행으로 계산한다. 평가 시작의 시설/관망 상태와 원 누적량을 보존하고, 시작 저류와 이후 누적 차분으로 각각의 수지를 제공한다. 유출/라우팅 시각이 다르면 평가 시작 상태를 임의 추정하지 않는다. 시간별 표시 프레임에서 첨두를 만들어내지 않으며, 2D 지표 초기화와 운영 순위 게시를 포함하는 경로가 아니다.

```sh
tmp/flood-venv/bin/python scripts/build_facility_swmm.py
INITIALIZED_FACILITY_EVIDENCE_DIR=data/runs/initialized-facilities-new PYTHONPATH=simulation \
  tmp/flood-venv/bin/python -m unittest simulation.tests.test_initialized_facilities
```

`forcing/coupled_initialization.py`는 같은 관측 초기화를 `run_coupled`의 시설·관망·지표 연속 실행으로 연결한다. 원 요청의 `initialization.method=OBSERVED_COUPLED_ANTECEDENT_CONTINUOUS_V1`, `observedRainfall.stationByCatchment`·`evaporationReference`, 지표의 동일 증발산 출처가 필요하다. 원 INP는 선행 시작부터 평가 종료+1초까지를 명시해야 하며 외부 시계열도 전체 기간을 충족해야 한다. 평가 원 지표는 선행 기간을 제외하고 내부 단계에서 집계하며, 시작 상태·누적 차분·침투 상태·요청/파생 입력을 함께 보관한다.

`dryExchangePolicy=BOUNDED_DRY_TAIL_ROUNDOFF_V1`은 침투 후 마른 유입부에 남는 직전 유량 적분 꼬리를 별도 수치 잔차로 기록한다. 1회 10⁻⁹m³·전체 10⁻⁸m³보다 큰 부족은 실패한다. 물리 제원이나 강우를 바꾸지 않으며, 기존 엄격 정책과 실패 산출물도 보존한다. 아래 검사는 실제 2022 관측을 합성 지형/관망에 적용한 것으로 서울 현장 침수 검증이나 운영 작업 게시가 아니다.

```sh
INITIALIZED_COUPLING_EVIDENCE_DIR=data/runs/initialized-coupling-new PYTHONPATH=simulation \
  tmp/flood-venv/bin/python -m unittest simulation.tests.test_initialized_coupling
```

보관한 성동 421의 선행 14일 원문과 2022-08-08 평가 강우·서울 108 기상 필요. 시험은 같은 합성 2ha 형상에서 7/14일·시들음점/포화 시드와 재생을 비교한다. 식생수로의 미지원 InitSat은 0으로 유지하며 그 시드까지 변경했다고 표시하지 않는다. 28일은 입력 형식을 지원하지만 해당 관측이 확보되지 않은 실행은 거부한다. 자료 없는 기간의 무강우 대체·다른 관측소 자동 대체는 없다.

## 연결 시설의 공개 견적

`engine/priced_facilities.py`는 연결 설계의 개별 이용조 용량을 `facilities/cistern-costs-v1.json`의 2.35m³ 견적과 대조한다. 수량은 배치된 개별 시설 개수로 계산하며 용량에 비례한 가격 외삽이나 단일 대형 저장조의 소형 설비 환산은 거부한다. 물리 계산에 넣는 면적·배수구·저류 깊이는 명시적 설계 입력이고 견적 문헌의 실측 치수가 아니다. 같은 물리 설계에서 견적 업체 변경은 INP를 바꾸지 않는다.

```sh
PYTHONPATH=simulation tmp/flood-venv/bin/python scripts/compare_connected_facilities.py \
  --design simulation/tests/fixtures/priced-cisterns-v1.json \
  --costing simulation/tests/fixtures/priced-cistern-request-v1.json \
  --output data/runs/priced-cisterns-new
```

보관한 서초 연구 원본과 별도 시설 관측 엔진 필요. 원가 요청의 전체 참조를 먼저 검사하고, 기준안·개별 시설·이용조 개방안·공동안을 실행한다. 원문의 견적 항목·미분류 차액·문헌 유지비·미산정 시설 ID·원가 해시·원문/코드가 결과에 포함된다. 견적 부분합과 연간 비용은 분리되며 총공사비·현행 단가·재해 당시 가격은 미확정. 운영 설치/예산 차감/순위에 사용하는 경로가 아니다.

## 직접 AWS 응답의 지표 계산

`run_live_surface.py`는 입력 JSON의 `mode`(`surface`/`coupled`), 명시적인 `model`, `rainfall`의 `startUtc`·`endUtc`·`stationByTriangle`·`assignmentEvidence`를 사용한다. 현재 관측은 공식 API에서 가져오며 서버의 유효한 동일 원문을 공유하고, 시간대/시계/소유권/분 관측을 검사한 뒤 실행 입력에 보존한다. 기본 `KMA_API_KEY` 하나만 사용하며 API·워커 합계 일 18,000회·4.5GB에서 수집을 중단한다. 공식 20,000회·5GB 한도에 10% 여유를 두고 소진·접근 실패 시 다른 키로 전환하지 않는다. 인증키를 저장 입력·로그·수치 엔진 자식 프로세스에 넣지 않는다.

```sh
tmp/flood-venv/bin/python scripts/run_live_surface.py \
  --input path/to/explicit-surface-request.json --output data/runs/new-surface-run
```

위 경로는 사용자가 마련한 명시적 입력 경로이며 제공된 실제 서울 모형을 뜻하지 않는다. 기본 집수 관망의 직접 응답 결속은 구현했으며, 실제 서울 모형 등록·현재 증발/풍응력·현장 경계 검증은 남아 있다. 자동 서울 침수 개방 명령은 아니다. `verify_live_surface.py --output data/runs/new-live-verification`은 최신 10분의 2관측소 응답과 이미 확보한 2022년 호우 원문을 합성 폐쇄 수조에 적용하는 수치 진단이다. 운영 지도·순위에는 기록하지 않는다. 오프라인 재생에는 실행의 `observed-surface-input.json`을 읽어 `forcing.surface_run.run_observed_surface(surface, observedRainfall, 새_출력_경로)`를 호출한다. 이 경로는 원문 해시와 분량을 다시 검사하며 API를 호출하지 않는다.


## 공개 현재 지표 결과 워커

```sh
# flood 선택 의존성과 고정 관망 관측 바이너리가 설치된 별도 Python 환경
# 회원 작업 큐와 별도 프로세스, API와 같은 ARTIFACTS_PATH 사용
tmp/flood-venv/bin/python scripts/run_public_surface.py --once
# 반복 처리 시 --once 생략
```

백엔드와 같은 SHA-256 고정 `surface/public-models-v1.json`만 읽는다. 현재 운영 목록은 비어 있으므로 위 명령은 API 조회·계산·게시 없이 종료한다. 격리 시험 자료를 이 목록에 등록하지 않는다. 컨테이너의 기존 회원 워커 이미지에는 이 별도 ANUGA 실행 환경을 추가하지 않았으며 자동 실행 서비스로 오인하지 않는다.

등록 항목의 `inputBundleSha256`에 해당하는 `data/public-surface/<hash>/manifest.json`과 모든 원 파일을 검사한다. `recipe.json`은 모형·고정 시작/평가 시각·강우 배정을, `numerical-policy.json`은 모형 원형 해시와 `engineSha256`을 고정한다. `input-evidence.json`에는 좌표/수직 기준·지형·관망·자산·외부 경계·건조/습윤 시드·더 긴 선행 기간 비교의 보관 파일 참조가 필요하다. 파일 존재·해시 검사는 현장 검증이나 수치 수렴 심사를 자동 대체하지 않는다. 실제 공개 근거 검토를 거친 버전만 코드의 고정 목록에 반영한다.

`CONTINUOUS_REPLAY_FROM_FROZEN_ORIGIN_V1`은 선행 7~28일을 포함한 같은 초기 상태부터 기존 사용 응답과 새 구간을 재생한다. 선행 기간은 평가 지표에서 제외한다. 이전 실행 이후의 구간만 공식 API에서 직접 조회하며 겹치는 분이 달라지면 거부한다. 실제 엔진 메모리의 체크포인트 복구는 아니며 최대 29일·응답 32MiB·관측소×분 100,000 한도를 넘으면 실패한다. 장기 실행 속도와 시즌 경계 이후 무기한 상태 유지의 완료 증거가 아니다.

유역별 실행 잠금·고유 실행 폴더·원자적 게시 인덱스를 사용한다. 게시 후 상태 저장 전 종료는 게시 원 묶음에서 복구하고, 손상된 계보를 새 건조 시작으로 바꾸지 않는다. 원 입력·관망 강우·전체 산출물 해시·고정 엔진·수치 통과·평가 완료·지도 범위·최종 시각 검사를 통과해야 공개한다. 120초 계산 제한·5분 최신성 제한 초과 시 게시하지 않으며 수치 간격/격자를 자동 완화하지 않는다. 원 코드·사용 응답·입출력·원 프레임·이전 실행 계보와 실패는 보존한다. 현재 풍응력/증발 및 추가 시설 조합, 실제 서울 유역 게시·장기 성능은 별도 남은 범위다.
