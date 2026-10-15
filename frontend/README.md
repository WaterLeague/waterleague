# 지역 탐색 프리뷰

Node 22.13 이상, pnpm 11.25.0.

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm build
pnpm dev
```

http://127.0.0.1:5173 에서 확인. 실제 성수동 OSM 건물 94개·원본 조회·선택·탑뷰·키보드 목록, 공개자료 QC·연구 원칙 화면 제공. 정적 스냅샷으로 동작하며 Spring API·회원·전략·공식 계산은 아직 연결하지 않음. 로컬 데이터 파생 스크립트는 루트 scripts/prepare_public_data.py.

표고 평탄화·일부 높이·도로 폭은 표현용 가정. 화면 면적은 공식 설치면적 아님. 원본 출처·해시·이용조건은 data/README.md 참조. 설치·SWMM·랭킹은 미구현 상태를 명시. 3D 번들은 지연 로딩, WebGL 실패 시 목록 대안. 브라우저의 R3F 내부 THREE.Clock deprecation 경고는 의존성 이행 항목으로 추적.
