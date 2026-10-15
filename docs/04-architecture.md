# 도메인·레이어 아키텍처

동일 출처 HTTPS의 React 앱·Spring Boot API, PostgreSQL/PostGIS, 격리된 Python SWMM 워커. Oracle 4 OCPU·24GB의 모듈형 모놀리스로 시작. 측정된 필요에 따라 분리.

초기 작업 큐는 PostgreSQL 트랜잭션·lease 기반. 전략 저장과 Redis enqueue의 이중 쓰기를 피하고, 필요 시 outbox로 Redis Streams 연계. Redis는 초기 필수 구성 아님. 세션은 프레임워크 기반 서버 저장.

## 도메인

| 도메인 | 책임 |
| --- | --- |
| identity | 회원·인증·세션·역할 |
| organization | 기관 검증·소속·초대 |
| catalog | 맵·셀·시설·강우·출처 |
| model | 수문모델·가정·검증 승인 |
| strategy | 불변 배치·변경 이력·활용 동의 |
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
