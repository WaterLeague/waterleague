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
