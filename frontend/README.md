# WATER LEAGUE 프론트엔드

React·TypeScript·Vite·R3F/Three.js. 도메인별 화면·상태 제어·규칙·API 접근을 분리한다. [로컬 게임](http://127.0.0.1:5173/weekly)은 주간 서울 대항전·재해 모드·랭킹·대회·데이터와 권한별 관리자 화면을 제공한다. 일반 지도 설치는 7종이다. 기관 리그와 미사용 연구실 화면은 제거했으며 현재 공개 범위는 [제품 계약](../docs/01-product.md)을 따른다.

저장소 루트의 [로컬 실행](../README.md#로컬-실행)로 API·워커·프론트를 함께 준비한다. 프론트만 실행할 때는 이 디렉터리에서 다음을 사용한다.

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm build
pnpm dev
```

`/api`는 로컬 8080 API로 프록시한다. 계산에는 Python 워커가 필요하다. [공통 화면·조작](../docs/08-experience.md), [지도 캐시·장애 복구](../docs/04-architecture.md), [1차 출시 범위·후속 개선](../docs/09-delivery.md)을 기준으로 수정한다.

`GamePage`와 `shared/controller/useAppLocation.ts`가 History API로 [페이지별 주소](../docs/08-experience.md#페이지-주소)를 처리한다. 기본 링크의 새 탭 동작과 뒤로/앞으로 이동을 유지하고, Vite·Caddy의 SPA 처리가 상세 주소 새로고침을 지원한다. 전체화면 대상은 `CityExplorer`의 게임 상단 바·지도·게임 조작부이며 버튼은 게임 시각 오른쪽에 둔다.

공개 지도·표시용 형상/물결·계산 프레임을 구분한다. 카메라 이동은 재계산을 유발하지 않으며 설치·예산·점수·권한은 서버가 검증한다. 토큰을 localStorage에 저장하지 않는다. 실제 기기 성능과 접근성 검증 결과는 [검증 기록](../docs/12-validation-log.md)에 남긴다.

지도 원문 해석·검증은 전용 Web Worker에서 수행하고 도시 지도용 기기 캐시를 최대 256MiB로 보관한다. 비 입자는 원 경계 색인과 GPU 낙하를 사용해 입자 수·위치를 유지한다. 저장소 실패·취소·해시 검증과 측정 범위는 [캐시 계약](../docs/04-architecture.md#지도-장애-복구와-캐시), [성능 검증](../data/benchmarks/rain-render-performance-v1.json)을 따른다.
