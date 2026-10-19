# WATER LEAGUE 프론트엔드

React·TypeScript·Vite·R3F/Three.js. 도메인별 화면·상태 제어·규칙·API 접근을 분리한다. [로컬 게임](http://127.0.0.1:5173/)은 주간 서울 대항전, 재해 실험·기록 경쟁, 데이터 화면을 제공한다. 일반 지도 설치는 6종이며 기관 리그/연구실의 현재 공개 범위는 [제품 계약](../docs/01-product.md)을 따른다.

저장소 루트의 [로컬 실행](../README.md#로컬-실행)로 API·워커·프론트를 함께 준비한다. 프론트만 실행할 때는 이 디렉터리에서 다음을 사용한다.

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm build
pnpm dev
```

`/api`는 로컬 8080 API로 프록시한다. 계산에는 Python 워커가 필요하다. [공통 화면·조작](../docs/08-experience.md), [지도 캐시·장애 복구](../docs/04-architecture.md), [확장 계획](../docs/09-delivery.md)을 기준으로 수정한다.

공개 지도·표시용 형상/물결·계산 프레임을 구분한다. 카메라 이동은 재계산을 유발하지 않으며 설치·예산·점수·권한은 서버가 검증한다. 토큰을 localStorage에 저장하지 않는다. 실제 기기 성능과 접근성 검증 결과는 [검증 기록](../docs/11-validation-log.md)에 남긴다.
