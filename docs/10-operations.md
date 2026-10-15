# Oracle 운영

목표 Oracle 4 OCPU·24GB, ARM64 가능성 포함. WebGL은 사용자 브라우저, SWMM은 서버 CPU. 실제 OS·디스크·네트워크는 배포 전 확인.

| 구성 | 초기 예산 제안 |
| --- | --- |
| reverse proxy·정적 파일 | 약 512MB |
| Spring Boot | heap 4GB, 컨테이너 여유 별도 |
| PostgreSQL/PostGIS | 약 4GB |
| SWMM worker | 동시 1·약 3GB |
| OS·파일캐시·피크·백업 | 잔여 |

실측 보장 아님. PostgreSQL 큐로 Redis 초기 선택 사항. CPU·메모리·실행시간 측정 뒤 동시성 조정.

외부 HTTPS, DB·워커 내부망, SSH 제한·forwarded header 신뢰 경계. 개발 HTTP 쿠키는 local 전용, 운영 오설정 시작 거부. 모델·이미지 digest·실행 아키텍처 고정.

미션별 셀·강우기간·보고간격·timeout·결과크기 상한. 사용자 큐 제한·lease heartbeat·재시도·dead letter. 실패 결과를 점수 0으로 순위 반영 금지. 결과 캐시와 권한·동의 분리. 임시파일 정리 전 재현 산출물 영속·해시 검증.

API 오류·지연, 큐 길이·대기·실행, 품질 거부, DB·디스크·인증·export 감사 모니터링. 생존·준비 체크 분리·민감정보 차단.

DB·모델·출처·결과 백업, 암호화·키 분리·복원 훈련. 복원 뒤 관계·해시·랭킹 재계산 확인. RPO/RTO와 단일 서버 장애 시 제출·마감 정책은 운영 전 정의.

배포 전 의존성·secret·권한·migration·backup·ARM64 SWMM·수치 회귀·성능 확인. 모델 변경과 코드 배포 분리, 진행 리그 입력 자동 덮어쓰기 금지. 이전 이미지 복귀와 DB 호환성 검증.
