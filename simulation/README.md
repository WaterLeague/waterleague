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
