# 공개자료 탐색 기록

2026-10-15 실제 다운로드 원본에서 생성. `manifests/public-data-audit.json`에 URL·SHA-256·취득시각·변환 스크립트 해시·제약 보존. 원본은 `raw/`에 로컬 저장, Git 제외.

- 성수동 OSM: 원본 375,364바이트, 후보 경계 내 way 건물 94개. 실제 footprint만 활용, 수문모델 미승인. OSM 높이 표기도 현장 실측 확인을 의미하지 않음.
- NOAA 서울 2024: 원본 2,969,340바이트, 관측 레코드 8,430개. AA1~4에 1·3·6·12·24시간 누적과 결측 코드 혼재. 이 자료의 QC·이벤트 연속성이 검증되지 않아 시뮬레이션 입력으로 사용하지 않음.
- 원본 확보와 공식 기상청·GIS·DEM·피복·배수 자료 확보는 별도. NOAA 자료를 기상청 API 취득 자료로 표기하지 않음.

## 원본 재취득·생성

```sh
mkdir -p data/raw
curl --fail --location --max-time 60 'https://api.openstreetmap.org/api/0.6/map?bbox=127.0525,37.5430,127.0555,37.5455' -o data/raw/seongsu.osm
curl --fail --location --max-time 60 'https://noaa-global-hourly-pds.s3.amazonaws.com/2024/47108099999.csv' -o data/raw/seoul-2024.csv
python3 scripts/prepare_public_data.py
```

실시간 갱신 출처를 재취득하면 해시가 달라질 수 있다. 과거 실험은 보관된 원본 스냅샷으로 재현. 이 스크립트는 승인된 모델 생성·강우 보간·SWMM 입력 생성을 수행하지 않는다.

## 이용조건

OSM 원본 및 파생 형상은 © OpenStreetMap contributors, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). 파생 데이터 전체는 `frontend/public/data/seongsu.json`에 포함하며 같은 라이선스로 제공. [출처 표시](https://www.openstreetmap.org/copyright) 유지.

NOAA 자료의 항목·품질코드는 [NCEI ISD 안내](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)와 [ISD 명세](https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf) 참조. 연구 입력 채택 전 이용조건·변수 정의·품질코드·누락을 별도 검토.

## 기상청 분자료

비밀 설정은 프로젝트 루트 `.env.local` 한 곳 사용. `.env.example`을 복사하고 `KMA_API_KEY` 설정. 실제 파일은 Git 제외. 환경변수가 파일보다 우선. AWS 매분자료 API 활용신청 필요.

```sh
simulation/.venv/bin/python scripts/fetch_kma.py
simulation/.venv/bin/python scripts/prepare_kma_event.py
```

서울 108 관측소, 2024-07-18 05:00~23:59 KST의 1,140개 누적 관측에서 1,139개 분당 강우 깊이 추출. 총 109.7 mm, 마지막 강우 15:40. 15분·60분 이동 누적과 교차 검증. 자정 리셋·결측·음수·불연속 거부. 출처: 기상청 AWS 매분자료. 원자료 해시는 `data/manifests/kma-108-202407180500-202407182359.json`, 파생자료는 `data/derived/kma-event.json`.

AWS 응답은 별도 QC 플래그를 포함하지 않으므로 자체 검사 결과를 기상청의 최종 품질 승인으로 표현하지 않음. 서울 관측소와 성수동의 거리·공간 대표성, 선행 함수 상태는 검증 전. 실제 강우를 사용한 EXPLORATORY 계산만 허용.

## 공식 지형·토지피복 원본

2026-10-17 사용자 직접 다운로드한 성동 37705의 2024/2025 DEM과 성동083의 2024 세분류 토지피복 확보. 원본은 `private/seongsu-official-20261017/`에 보존, Git 제외. 원본 구성 파일 hash·검사 도구 버전·품질 제한은 `manifests/seongsu-spatial-audit.json`, 검사 방법/결과는 [문서 28](../docs/28-spatial-source-audit.md) 참조.

DEM은 90m 격자이며 수직 기준·표고 단위 필드 미제공. 토지피복은 잘못된 도로 도형이 실험 구역에 영향을 줄 수 있어 부분 면적만 계산. 원본 자동 복구·모델 편입·공개 배포 없음. 등록된 ZIP의 hash를 확인하는 `scripts/audit_spatial_sources.py`로 로컬에서 재검사. 원본/파생 좌표 재배포 조건과 정밀도 검토 후 새 모델 버전 결정.

별도 `scripts/diagnose_landcover_topology.py`로 원본을 보존한 두 보정 후보 진단. 오류 도로 2개를 포함하면 구역 내 175개 도형, 부동소수 오차 범위에서 전체 영역 포함. 두 방식의 분류별 대칭차 0m², 현장 정확성·불투수율·침투율 검증은 아님. 좌표를 제외한 요약은 `manifests/seongsu-topology-diagnostic.json`. 운영 모델 채택 없음.

## EPA 참조 사례

`benchmarks/epa-applications-example1.json`은 EPA Applications Manual의 Example 1 원본·인쇄 수치·충돌·판정 계약이다. `benchmarks/epa-applications-example1-result.json`은 고정 SWMM 5.2.4 실행의 공개 요약. 원본은 공식 주소에서 hash 검증 후 로컬/CI로 재취득한다. 미국 설계강우 교육 사례이며 서울 관측이나 시설 효과 자료로 혼용하지 않는다. 국제단위 변환·인쇄 참조 차이는 검토 필요 상태로 보존. 재현 명령과 판정 범위는 [문서 32](../docs/32-epa-reference-validation.md) 참조.
