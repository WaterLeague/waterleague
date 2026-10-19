# 공개자료 탐색 기록

이 파일은 저장/재취득 방법과 초기 성수 자료의 기록이다. 현재 서울 전역 지도·6종 시설·3개 재해 사건까지의 자료 목록은 [자료 계보](../docs/03-data-provenance.md), 확보 여부는 [접근 현황](../docs/13-data-access.md)을 따른다. 아래 초기 표본의 수량/한계를 현재 전체 범위로 읽지 않는다.

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

비밀 설정은 프로젝트 루트 `.env.local` 한 곳 사용. 새 환경에서만 `.env.example`을 복사하고 `KMA_API_KEY`를 설정한다. 기존 `.env.local`과 승인된 키는 유지한다. 실제 파일은 Git 제외. 환경변수가 파일보다 우선. 처음 수집하는 환경에는 AWS 매분자료 권한이 필요하다. 현재 프로젝트의 승인된 권한을 다시 신청하지 않는다.

```sh
simulation/.venv/bin/python scripts/fetch_kma.py
simulation/.venv/bin/python scripts/prepare_kma_event.py
```

서울 108 관측소, 2024-07-18 05:00~23:59 KST의 1,140개 누적 관측에서 1,139개 분당 강우 깊이 추출. 총 109.7 mm, 마지막 강우 15:40. 15분·60분 이동 누적과 교차 검증. 자정 리셋·결측·음수·불연속 거부. 출처: 기상청 AWS 매분자료. 원자료 해시는 `data/manifests/kma-108-202407180500-202407182359.json`, 파생자료는 `data/derived/kma-event.json`.

AWS 응답은 별도 QC 플래그를 포함하지 않으므로 자체 검사 결과를 기상청의 최종 품질 승인으로 표현하지 않음. 서울 관측소와 성수동의 거리·공간 대표성, 선행 함수 상태는 검증 전. 실제 강우를 사용한 EXPLORATORY 계산만 허용.

## 공식 지형·토지피복 원본

2026-10-17 사용자 직접 다운로드한 성동 37705의 2024/2025 DEM과 성동083의 2024 세분류 토지피복 확보. 원본은 `private/seongsu-official-20261017/`에 보존, Git 제외. 원본 구성 파일 hash·검사 도구 버전·품질 제한은 `manifests/seongsu-spatial-audit.json`, 검사 방법/결과는 [문서 19](../docs/19-spatial-source-audit.md) 참조.

DEM은 90m 격자이며 수직 기준·표고 단위 필드 미제공. 토지피복은 잘못된 도로 도형이 실험 구역에 영향을 줄 수 있어 부분 면적만 계산. 원본 자동 복구·모델 편입·공개 배포 없음. 등록된 ZIP의 hash를 확인하는 `scripts/audit_spatial_sources.py`로 로컬에서 재검사. 원본/파생 좌표 재배포 조건과 정밀도 검토 후 새 모델 버전 결정.

별도 `scripts/diagnose_landcover_topology.py`로 원본을 보존한 두 보정 후보 진단. 오류 도로 2개를 포함하면 구역 내 175개 도형, 부동소수 오차 범위에서 전체 영역 포함. 두 방식의 분류별 대칭차 0m², 현장 정확성·불투수율·침투율 검증은 아님. 좌표를 제외한 요약은 `manifests/seongsu-topology-diagnostic.json`. 운영 모델 채택 없음.

13개 배치 구역의 피복·수치지도 건물 대조는 `scripts/audit_cell_landcover.py`, 공개 집계는 `manifests/seongsu-cell-landcover-audit.json`. 원본/모델/코드/상세 결과 해시와 구역별 면적·분류·자료 간 불일치를 보존. G1의 건물 중첩, G3/G5의 철도 분류 및 옥상 경계 차이 확인. 기존 가정 구역을 현실 설치 가능 부지로 채택하지 않으며 새 모델의 후보 재선정 근거로 사용.

## 수치지형도와 서비스용 저장 자료

현재 화면 표기는 ‘2026-03-07 갱신 수치지형도’다. 브이월드 성동구 SHP 묶음 95도엽 중 아래 기존 4개 ZIP 및 내부 660파일 전체 일치를 확인했다. 배포 갱신일과 제작연도는 구분하며 [배포 대조 기록](manifests/vworld-seongdong-topography-20260307.json)에 출처·해시·적용 범위를 보존한다. 새 원본 묶음은 `private/vworld-seongdong-topography-20260307/`에 보관하고 Git에서 제외한다.

2025년 1:1,000 수치지형도 4개 ZIP·4개 XML 및 추가 DXF·XML을 `private/seongsu-topography-20261017/originals/`에 복사하고 다운로드 원본과 해시 대조. 파일 10개의 출처·크기·SHA-256은 `manifests/seongsu-topography-sources.json`. 원본은 프로젝트에 보관하며 Git 제외, 서비스용 가공본과 출처 목록은 Git 포함.

```sh
simulation/.venv/bin/python scripts/prepare_topography_buildings.py --check
```

국토지리정보원 [수치지도V2.0](https://www.data.go.kr/data/15059719/fileData.do), 공공누리 제1유형(출처표시). 건물 `N1A_B0010000` 레이어 2,737도형 중 연구 영역과 양의 면적으로 교차하는 246도형을 선택. EPSG:5186 원문 PRJ와 CP949 속성을 읽고 검증한 EPSG:4326 경계·명칭·층수를 `backend/src/main/resources/spatial/seongsu-buildings.json`에 보관. 도형을 영역 경계로 자르거나 도엽별 조각을 병합하지 않음. 좌표 변환 근거와 해시는 `manifests/seongsu-topography-buildings.json`.

API 서버는 고정 건물 스냅샷의 SHA-256·도형·메타데이터를 검사해 재사용한다. 과거 기상은 보관 원본/파생자료를 사용하고 주간 KMA·현재 서울 도시자료만 제한된 서버 실시간 경로로 조회한다. 브이월드 실시간 건물 조회는 제거했으며 외부 키는 브라우저/계산 자식 프로세스에 전달하지 않는다. 새 자료는 별도 취득·검사 후 버전 갱신하며 과거 실행에 사용된 원본과 모델은 보존.

성수 수치지형도 연구 모델의 경계 후보는 `derived/seongsu-topography-candidates-v2.json`. `scripts/prepare_topography_candidates.py --check`가 원본 4개 도엽을 다시 읽어 같은 결과인지 검사한다. 건물 경계 기반 옥상 8개와 도로면 내부의 25m² 지상 5개, 건물·철도·교량 접촉 제외. 원본 ID/CRS/좌표/파생 면적/선정 정책 보존. 수치지형도 연구 모델에 연결됐으나 실제 지붕·구조 하중·시공 허가·투수율·배수 연결을 검증했다는 의미가 아니다.

## EPA 참조 사례

`benchmarks/epa-applications-example1.json`은 EPA Applications Manual의 Example 1 원본·인쇄 수치·충돌·판정 계약이다. `benchmarks/epa-applications-example1-result.json`은 고정 SWMM 5.2.4 실행의 공개 요약. 원본은 공식 주소에서 hash 검증 후 로컬/CI로 재취득한다. 미국 설계강우 교육 사례이며 서울 관측이나 시설 효과 자료로 혼용하지 않는다. 국제단위 변환·인쇄 참조 차이는 검토 필요 상태로 보존. 재현 명령과 판정 범위는 [문서 20](../docs/20-epa-reference-validation.md) 참조.
