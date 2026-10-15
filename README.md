# WATER LEAGUE

실제 공개자료와 수문 시뮬레이션을 기반으로 시민이 물환경 개선 전략을 설계하고, 정부·기관이 재현 가능한 후보안을 연구하는 웹 3D 게임.

**우선순위: 현실 적합성 → 재현성 → 공정성 → 사용성 → 시각 품질.** 엔진 실행 성공을 현장 정확성 검증으로 취급하지 않는다.

## 문서

- [제품 요구사항](docs/01-product.md)
- [연구 적합성·모델 검증](docs/02-scientific-validity.md)
- [공개데이터·출처 관리](docs/03-data-provenance.md)
- [도메인·레이어 아키텍처](docs/04-architecture.md)
- [데이터 모델](docs/05-data-model.md)
- [API·오류 계약](docs/06-api.md)
- [보안·권한](docs/07-security.md)
- [3D·UX 설계](docs/08-experience.md)
- [구현 단계·완료 기준](docs/09-delivery.md)
- [Oracle 운영](docs/10-operations.md)
- [Git·개발 규칙](CONTRIBUTING.md)
- [설계 결정](docs/decisions/0001-foundation.md)

## 목표 구성

| 구성 | 기술·역할 |
| --- | --- |
| `frontend/` | React·TypeScript·Three.js, 플레이·결과·기관 화면 |
| `backend/` | Java·Spring Boot, 인증·규칙·전략·공식 평가 |
| `simulation/` | Python·EPA SWMM, 격리 계산·품질 검증 |
| PostgreSQL·PostGIS | 공간자료·회원·불변 실험·작업 큐 |
| Oracle 4 OCPU / 24GB | CPU 서버, 워커 초기 동시성 1 |

첫 맵은 서울의 소규모 블록 후보에서 관측·배수·검증 자료 가용성을 기준으로 선정한다. 최종 대상지와 현장 검증은 별도 단계다.

게임 결과는 지정 모델·입력·가정 아래의 예측값이다. 연구자는 입력 원본, 배치, 모델·엔진 버전, 검증 보고서, 불확실성, 실행 기록을 함께 사용한다. 점수만으로 현실 설치 효과나 시공 적합성을 판정하지 않는다.

현재 계획과 구현 상태는 [작업 현황](docs/09-delivery.md)에서 구분한다. 확보하지 않은 관측값·검증 결과·랭킹은 생성하지 않는다.
