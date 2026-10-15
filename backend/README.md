# API 기반

Java 25·Spring Boot 4.1.1·Maven Wrapper.

```sh
./mvnw test
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

JDK 25가 필요하다. macOS에서 여러 JDK를 사용하는 경우 `JAVA_HOME=$(/usr/libexec/java_home -v 25)` 설정. 기본 바인딩 127.0.0.1:8080. 운영 HTTPS 쿠키 설정과 local HTTP 설정 분리.

구현: 공개 출처 카탈로그, 빈 승인 맵 목록, 도메인 배치·예산 검증, 모델 등급·검증 범위 게이트, 수치 품질·점수 산식, 공통 Problem Details·보안 기본 거부.

공개 API: GET /api/v1/catalog, GET /api/v1/maps, GET /actuator/health. 회원·저장·SWMM·공식 제출 API는 아직 제공하지 않는다. 기본 테스트 계정이나 관리자 우회 없음. 현재 카탈로그는 출처 안내이며 승인된 실제 맵을 생성하지 않는다.

점수 서비스는 검증 계약의 단위 구현이며 운영 SWMM 결과 연결·실험 문맥 해시 일치·DB 권한 검증은 후속 단계다.
