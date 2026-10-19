# 도메인·레이어 아키텍처

## 도시 장면 도메인 (2026-10-19)

`frontend/src/domains/urban`은 repository의 해시·Zod 검증, controller의 도로 타일/인구 로딩과 재생 시각 ref, service의 태양/인구/경로/도로 형상 수학, view의 조명·도로·보행/차량·창문 재질로 분리한다. API키·새 외부 브라우저 요청·의존성 추가 없음. 고정된 카탈로그 해시→타일별 해시를 확인하고 경로·크기·좌표·객체 수를 제한한다.

도로는 카메라 구간 변경 시 150ms 조정 조회, 이전 요청 취소, 25타일 캐시, ID 중복 제거를 적용한다. Worker에서 지형 삼각면에 정합한 도로 표면을 생성하고 교체 이후 이전 GPU 형상을 해제한다. 도시 객체는 인스턴싱으로 최대 차량 300·보행자 180·가로등 500개, 근처 후보 1,600개만 사용한다. 시선과 선분 사이 거리로 긴 도로도 선택한다. 프레임별 React 상태 변경 없이 공통 demand 렌더와 시각 ref를 사용하며 인구 배분은 구/시간 단위로 캐시한다.

태양 uniform·장면 조명·빗방울은 수면 캡처보다 먼저 갱신한다. 그림자 범위는 시야 거리에 맞추고 지도 전체/밤에는 끈다. 주간 천문 시계는 1초, 연속 교통은 기존 30Hz 수면 깨움과 공유한다. 과거 시각 변경은 구독자 invalidate로 즉시 반영하고 일시정지에서는 독립 타이머로 렌더하지 않는다. 장면 종료 시 타이머·구독·Worker·재질·형상 정리. 원 수문 계산·강우·시설 제원·점수 경로는 변경하지 않는다.

`backend/urban`은 121장소 고정 카탈로그 repository, 서울시 HTTPS repository, 원문 검증 mapper, 단일 진행 요청을 공유하는 service, 비회원 GET controller로 구성한다. 한 요청은 유효한 장소 ID 1~6개만 받으며 외부 연결은 최대 4개, 요청별 10초·본문 1MB·리디렉션 금지다. 성공 응답은 각 필드 유효기간 안에서 최대 5분, 부분 실패는 최대 1분 캐시한다. 인구와 교통의 실패는 독립적이며 자료 만료를 연장하지 않는다.

프론트는 250m 시야 단위·300ms 지연으로 가까운 최대 6장소를 선택한다. 1분 조회, 이전 요청 취소, 숨긴 탭/재해/원경 조회 중단을 적용한다. 실제 이동 지점이 공식 장소 안에 있을 때만 인구 범위의 중간값/면적으로 표시 예산을 계산하고, 유효한 장소 평균 속도를 차량 이동량에 적분한다. 0km/h 정지, 속도 갱신 위치 연속성, 장소 밖/만료 시 참고 프로필 복귀를 보장한다. 수면·빗방울은 같은 도시 시계의 사건 시작 기준 초를 사용하여 정지·배속·앞뒤 탐색과 연결한다. 주간 수면은 장면 시작 이후 실제 시간 차를 사용하고 모션 축소 시 정지한다.

동일 출처 HTTPS의 React 앱·Spring Boot API, PostgreSQL/PostGIS, 격리된 Python SWMM 워커. Oracle 4 OCPU·24GB의 모듈형 모놀리스로 시작. 측정된 필요에 따라 분리.

초기 작업 큐는 PostgreSQL 트랜잭션·lease 기반. 전략 저장과 Redis enqueue의 이중 쓰기를 피하고, 필요 시 outbox로 Redis Streams 연계. Redis는 초기 필수 구성 아님. 세션은 프레임워크 기반 서버 저장.

공개 관망 회원 연구는 `watershed` 도메인의 V20 불변 요청·서버 카탈로그·소유자 조회로 연결. `WATERSHED` 큐는 기존 입장 잠금/180초 lease/3회 한도/오래된 결과 차단을 공유하며 공용 활성 수에 포함. 독립 프로세스는 150초 벽시계·75초 프로세스 CPU·64MiB 파일 한도, 비밀 환경 미전달. 공개 원 관망의 수치 파생과 문헌 시설 컴파일러를 사용하여 기준안/공동안 2실행. 실패 결과도 보고서에 보존하고 계산 품질과 작업 완료 상태 구분. 실행 시점 코드·엔진·라이선스 포함 원 소스·파생/원 입력·프레임을 보관하며 모든 산출물의 해시를 DB 결과에 결속. 현재는 서버/워커 경로이며 공통 게임 화면의 설계·결과 연결은 다음 범위.

재해 시작 수분 비교는 별도 큐를 추가하지 않고 기존 historical 요청에 선택한 배치 한 곳과 `SELECTED_SURFACE_7_DAY_DRY_WET_V1` 정책을 고정한다. 워커의 일반 계산 후 같은 선행 관측·제원으로 `initialization_sensitivity.analyze(days=(7,))`를 실행하며, 비교 없는 요청은 기존 비용 유지. 결과는 일반 결과와 분리한 `initializationSensitivity`, 재현 파일은 같은 소유자 경계의 `sensitivity/`에 보존한다. 요청 대상 변경 멱등 충돌·추가 대상 수 제한·기존 CPU/시간/파일 크기 제한 유지. 화면은 공통 설치 패널과 물리 근거 컴포넌트 사용, 프레임 재생·지도 렌더가 추가 계산을 유발하지 않는다.

## 도메인

| 도메인 | 책임 |
| --- | --- |
| identity | 회원·인증·세션·역할 |
| organization | 기관 검증·소속·초대 |
| catalog | 맵·셀·시설·강우·출처 |
| model | 수문모델·가정·검증 승인 |
| strategy | 불변 배치·변경 이력·활용 동의 |
| cost | 설치 시점의 수량·공개 참고 단가·미산정 범위 스냅샷, 원문 해시·계산 입력 대조 |
| simulation | 작업·SWMM 결과·품질 판정 |
| league | 기간·참가·불변 규칙·제출 |
| ranking | 비교 집단·최고기록·동점 |
| research | 기관 열람·비교·재현·검토 |
| analysis | 동의된 원본의 기관 다강우 재계산·소유권 유지·선택 표본의 배치 패턴 기술 통계 |

## 구조

```text
frontend/src/
  app/                          라우팅·Provider·조합
  domains/<domain>/
    controller/                 React 상태·유스케이스 hook
    view/                       페이지·컴포넌트·3D
    dto/                        API 계약
    exception/                  도메인 오류
    service/                    순수 규칙·유스케이스
    mapper/                     DTO ↔ 내부 모델
    entity/                     내부 모델·불변식
    repository/                 API·저장 adapter
  shared/exception/             공통 오류·ErrorBoundary
  shared/http/                  쿠키·CSRF·추적
  shared/ui/                    토큰·공통 조작

backend/src/main/java/io/waterleague/
  <domain>/
    controller/                 REST 입력·출력
    view/                       공개 response record
    dto/                        요청·도메인간 전송 record
    exception/                  도메인 예외
    service/                    트랜잭션·권한·유스케이스
    mapper/                     entity ↔ DTO/View
    entity/                     영속 모델·불변식
    repository/                 영속 접근
  common/exception/             ErrorCode·예외·핸들러
  common/security/              인증·인가·보안 필터
  common/config/                설정

simulation/src/waterleague_sim/
  ingestion/                    수집·정규화
  model/                        모델 명세·LID 변환
  execution/                    격리 실행·timeout
  quality/                      물수지·지표·검증
  provenance/                   해시·재현 묶음
```

실제 책임이 생길 때 파일 생성. 이름만 있는 빈 클래스·중복 exception 디렉터리 금지. backend view는 JSON 표현이며 React와 중복 화면 템플릿 아님.

## 의존 방향

view → controller → service → repository. mapper는 DTO/entity/view 변환. 서버 service가 소유권·규칙·트랜잭션, entity가 불변식 담당. 다른 도메인 repository 직접 참조 제한, 공개 service/port·ID로 연결. 공통 영역은 기술 횡단 관심사로 제한. 프론트 순수 service는 React·fetch·Three.js에 비의존, renderer는 공식 점수 미계산.

## 실행 경로·일관성

입력 → 사용자·기간·동의·배치·예산·검증 수준 재검사 → 불변 전략과 작업 원자 저장 → `FOR UPDATE SKIP LOCKED` lease → 승인 모델 격리 계산 → lease token·입력 hash·품질 검증 → 결과 확정 → 자격 있는 공식 제출만 랭킹 반영.

at-least-once 작업 처리, run/hash unique·fencing token으로 결과 한 번 확정. 만료 워커 결과 거부. Idempotency-Key는 사용자·endpoint·요청 해시에 연결, 같은 키 다른 본문은 409. 제출 한도는 DB 트랜잭션으로 보호. 공식 제출·기관 열람 때마다 동의·권한 재검증.

## 버전

Java 25 LTS·Spring Boot 4.x·React 19·TypeScript·Three.js/R3F 안정 조합 후보. 설치 시 실제 안정 배포·호환성 확인 후 lockfile 고정. [Spring 시스템 요구사항](https://docs.spring.io/spring-boot/system-requirements.html) 확인. PostgreSQL/PostGIS·Python/SWMM은 ARM64와 수치 재현 검증 후 고정.

## 지표 원 계산 프레임

`engine/surface_frames.py`가 명시적 `frameOutput` 설정이 있는 계산에서만 격자 원형과 중심 수심/운동량을 읽기 전용 보관. `native-frames/catalog.json`은 입력·파일 해시·실제 출력 시각·수치 상태·좌표/수직 기준·출력 한도를 연결. 꼭짓점 xyz/중심 xyz/면적은 `<f8`, 삼각형 꼭짓점 색인은 `<u4`, 각 프레임은 삼각형 순서의 `[depthM, xmomentumM2s, ymomentumM2s]` 행렬 `<f8` little-endian. 좌표는 입력의 로컬/투영 좌표 그대로이며 서울 화면 좌표로 임의 치환하지 않음.

`engine/surface_frame_reader.py`는 외부에서 고정한 결과 해시→카탈로그→입력/격자/요청 프레임의 해시를 확인. 프레임 하나만 읽고 명시한 화면 범위와 교차 가능성이 있는 삼각형을 선택하며, 이 조회 범위가 계산 경계나 점수 영역을 바꾸지 않음. 수치 실패·파일 링크·경로 이탈·형식/크기/해시 불일치·시간 외삽은 도메인 예외. 공개/기관 API가 아니며 후속 서버 연결에서 작업 소유·동의를 매 요청 검사할 예정. 원 지표는 엔진 내부 집계에서 유지하고 화면 프레임으로 다시 집계하지 않음.

### 지표 결과의 공통 지도 전달

`presentation/surface_playback.py`는 `NativeFrameReader`로 전체 원본 무결성·수지를 확인한 뒤 원 지형 WKT·원점에서 도시 EPSG:5186 원점으로 수평 좌표만 변환한다. 비근사 변환을 사용하고 변환식·정확도 메타데이터 보존. 원 수심·운동량 바이너리를 그대로 복사하며 표시 지표 높이와 물리 기준고를 혼합하지 않는다. `surface-playback/catalog.json` 해시를 작업 결과에 고정한 실행만 서버 도메인의 repository→service→controller에서 조회한다. 요청마다 권한과 해시를 검사하며 권한 캐시는 사용하지 않는다.

공통 `CityExplorer`의 계산 침수 제어와 `SurfacePlan/SurfaceLayer`를 주간·재해 지도에 연결. 2D/3D는 동일 격자·수심/속력 색상표·실제 기록 시각 사용. 3D는 Worker의 Float32 표시 형상만 사용하며 원 Float64 계산값 불변. 표시 지형+2cm 위에 원 수심의 상대 두께를 1:1로 올리고 외곽·수심 단차의 측면을 생성한다. 수직 기준 계약 `TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION`을 유지하며 실제 절대 수면고로 승격하지 않는다. 지도 투영 전 운동량을 방향 화살표로 사용하지 않는다. 재해는 공통 강우 시간축과 연동, 주간은 선택한 본인 설치의 저장 프레임 조회. 시간 밖 외삽 금지, 이동 요청 250ms 조정 및 이전 요청 취소. 결과 없는 작업의 안내·좌표 원점 불일치·오래된 다른 실행 응답 거부. 결과 전체 정확도·30fps·서울 연결 유역의 운영 게시 완료는 이 전달 기능만으로 주장하지 않는다.


### 3D 수면 재질과 자원 수명

`WaterScene`이 모든 수면을 제외한 장면 색상·깊이를 프레임당 한 번 공유 캡처한다. 긴 변 1024px 상한, 화면 공간 반사 32보행·5회 교차 세분화, 화면 밖/고도 16km 초과의 하늘색 대체를 적용한다. 굴절은 깊이 재구성으로 전경 물체를 제외하며 수면의 depthTest/depthWrite를 사용한다. 형상·재질·깊이 텍스처는 해제하고 Worker는 완료/실패/교체 시 종료한다. 하천 경계·섬 구멍을 보존한 Worker는 먼저 표시 지형에 맞춘 뒤 80m 변을 목표로 분할하되 14단계·12만 삼각형 예산으로 제한하며 원 삼각형을 버리지 않는다. 원본이 예산을 넘는 경우 원본 보존이 우선이다.

공통 30Hz 요청 타이머와 demand 렌더를 사용하되 실측 30fps 보장을 뜻하지 않는다. 재해 일시정지·접근성 reduced-motion·숨긴 탭에서 공통 물결 시간을 멈춘다. 시각 파고·반사·굴절은 조회 프레임·점수·질량수지에 반영하지 않는다. 자연 하천 flow 속성은 0이며 관측 풍향은 물결 방향에만 사용한다. 지표 계산 flow는 기존 프레임의 투영된 유향×유속을 보존한다.

무풍·풍향 결측·관측 공백에서도 공통 시간에 따른 제자리 법선 진동을 유지한다. 바람이 유효할 때만 방향 위상을 더하며 풍향과 풍속의 유효성을 따로 판단한다. 서울 전체 축척에서는 화면 미분으로 넓은 법선 대역을 혼합한다. 제자리 진동과 축척별 대역은 반사·굴절의 시인성을 위한 표현이며 실측 파장·수위·유속 입력이 아니다.


`terrainDrapeService`는 표시 삼각형을 지형의 행·열·대각선과 교차 분할하고, `terrainMeshData`와 같은 삼각면 보간을 적용한다. 하천·침수 기록·계산 수심 상면과 측면에서 공유한다. 지형 외곽은 기존 가장자리 높이 고정을 유지하고 원 평면 범위는 자르지 않는다. 각 수면 형상의 위치 버퍼 9백만 성분 상한 초과 시 오류 경로로 반환하며 일부 영역을 조용히 생략하지 않는다. 원 계산 Float64 및 원 기록 파일은 불변이다.

`FloodTraceLayer`도 `WaterScene`에 등록하여 반사의 자기 참조를 제외한다. 기록에는 수심·유속을 만들지 않고 깊이 판정을 적용한다. 축척별 물결 법선·색상 대비는 실제 게임 지도 축척에서 식별되도록 구성한다. 하늘의 반사 패턴은 화면 밖 반사의 그래픽 대체이며 현재 구름 관측을 표현하지 않는다.
