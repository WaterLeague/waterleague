# 시뮬레이션 워커

공식 EPA SWMM 5.2.4 소스 커밋 고정 빌드, C API 실행과 PostgreSQL lease 큐. 사용자 입력은 서버가 검증한 시설 배치로 한정한다. 원본 INP·실행 경로·엔진 설정을 외부에서 받지 않는다.

```sh
# 저장소 루트
bash scripts/build_swmm.sh
uv sync --project simulation --locked
PYTHONPATH=simulation simulation/.venv/bin/python -m unittest discover -s simulation/tests -v
python3 scripts/run_local.py worker
```

`require_complete`는 시간대, 간격, 전체 구간, 관측소, 원본 ID, 품질코드, 비유한 값·음수·결측을 검증한다. 빈 관측을 무강우로 채우거나 누적기간을 임의로 재분배하지 않는다. 승인 품질코드는 각 제공기관 명세를 검토한 정책으로 전달해야 한다.

기상청 108 관측소의 실제 2024-07-18 05:00~23:59 KST 자료 사용. 일 누적 차분 1,139분·109.7 mm, 15분/60분 누적 교차 검증. 별도 제공기관 QC 플래그 부재와 부지 대표성 미검증 기록.

13개 표면의 독립 유출·LID 침투·저류 계산. 실제 배수관망·지형·현장 토양 모델 부재로 탐색 등급 유지. 표면 유출+LID 배수+최종저류−초기저류를 기준안과 비교한다. 기저 침투·초기 수분·시설 제원은 가정이며 범위 계산은 신뢰구간이 아니다.

작업당 90초 제한, CPU 75초, 파일당 64 MiB, lease 180초·최대 3회 획득·fencing. 운영 시 컨테이너 메모리·프로세스·디스크 한도 추가 필수. 결과 디렉터리는 `data/runs/<job UUID>/<lease UUID>`에 입력·출력·빌더·manifest 보존. `.env.local`의 키와 DB 비밀번호는 자식 실행 환경에서 제거.

엔진 테스트는 API/CLI 물수지 일치, 반복 재현, 3종 LID, 5초/10초 시간간격 민감도, 무강우 평가 거부를 확인한다. 현장 관측과의 독립 검증을 대체하지 않는다.

동일 조건의 성공 산출물은 `data/private/simulation-cache`에 최대 128개·2 GiB·7일 보관한다. 모델·배치·엔진·빌더·실행 정책·플랫폼이 일치하고 파일 해시를 통과한 경우에만 대상 작업의 새 산출물 경로에 복사한다. `request.json`·회원·메모·이력은 공유하지 않는다. `result.json.execution.mode`의 `REUSED`는 새로운 독립 검증이 아니다.

`.env.local`의 `SIMULATION_CACHE_PATH`는 비어 있는 전용 경로 사용, `SIMULATION_CACHE_ENABLED=false`로 비활성화. 캐시 삭제·손상·만료·잠금 경합은 재계산으로 처리한다. 계산 중에는 캐시 잠금을 보유하지 않아 동시 미스는 각각 실행할 수 있다. 워커 설정 변경 후 처리 중 작업이 없는 시점에 재시작. 캐시는 영구 재현 산출물 백업을 대신하지 않는다. 상세 계약은 `docs/24-simulation-cache.md` 참조.

## 관망·지표 엔진

`engine/network.py`는 별도 EPA DYNWAVE 빌드, `engine/surface.py`는 고정 ANUGA 4.0.1 실행. 기존 LID 바이너리와 운영 큐를 교체하지 않는다. 관망·2D를 같은 프로세스에 직접 로드하면 각 휠의 OpenMP 런타임이 충돌할 수 있으므로 `EngineProcess`를 사용한다. 상태는 자식 프로세스 안에 유지하며 부모는 허용된 입력·시간 전진·결과만 요청한다. 자식에 DB/API 비밀 환경을 넘기지 않는다. 강우 소유 영역 중복·외곽 경계 누락·비유한 값·평가 종료 누락은 실패 처리.

```sh
simulation/.venv/bin/python scripts/build_network_swmm.py
# 실행 중인 워커 환경을 보존하는 별도 선택 환경
UV_PROJECT_ENVIRONMENT="$PWD/tmp/flood-venv" uv sync --project simulation --locked --extra flood
MPLBACKEND=Agg tmp/flood-venv/bin/python scripts/verify_flood_engines.py \
  --output data/runs/flood-engine-reference-new
```

참조 실행에는 이미 확보한 `tmp/epa-reference/applications.zip` 사용. `--source`로 같은 해시의 원본 위치 지정 가능. 출력 디렉터리는 새 경로 필수. 관망 INP/RPT/OUT·상태 프레임·경계 변경과 지표 입력/수심/유속/SWW·엔진/코드 해시 보존. 실패 수치 사례도 manifest에 포함한다. 이 실행은 엔진 기반 확인이며 서울 관망·지표 결합이나 현장 침수 검증 완료를 뜻하지 않는다. 실제 양방향 교환·지표 침투/증발산·공개 관망 입력은 후속 연결 대상이다.
