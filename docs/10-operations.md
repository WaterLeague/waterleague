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

## 로컬 복원 훈련 계약

`verify_database_restore.py`는 운영 복구 명령이 아닌 격리된 복원 검사. 원본 DB의 REPEATABLE READ 스냅샷을 `pg_dump --snapshot`과 공유하고 새 `waterleague_restore_<무작위값>` DB에만 복원. 원본 DB 변경·기존 DB 덮어쓰기 금지. 생성한 DB만 마지막에 제거, 정상 종료·검사 실패 모두 임시 덤프 제거. 덤프 디렉터리 700·파일 600, 비밀값은 명령 인자·보고서·로그에 출력하지 않음.

세션·요청 제한 데이터는 덤프에서 제외하여 복원 후 전체 재로그인. 나머지 public 테이블은 정렬된 행 원문의 건수·SHA-256를 스냅샷과 대조. 마이그레이션 성공, 완료 계산별 불변 버전/입력/모델 hash·원화 비용·점수·재현 파일 manifest를 검사하고 같은 자료가 복원 DB에서 참조되는지 확인. 자료 디렉터리는 읽기만 수행. 실제 산출물을 다른 저장장치로 복원한 시험과 구분.

검증용 DB 생성 권한과 원본 DB major에 맞는 PostgreSQL 도구 필요. `PG_BIN`으로 도구 디렉터리 지정 가능. 별도 DB의 이름은 호출자가 지정할 수 없으며 작업자가 생성한 식별자와 일치할 때만 제거. 강제 종료 시 남을 수 있는 `waterleague_restore_` DB·임시 폴더는 보고서·로그의 식별자를 확인한 뒤 정리.

원격 호스트·지원하지 않는 연결 옵션 거부, 임시 저장공간 사전 확인. 보고서는 기존 파일을 덮어쓰지 않으며 실패/정리 필요 상태를 구분. 성공한 덤프도 훈련 종료 시 제거되므로 이 명령 자체를 백업 보관 수단으로 사용하지 않음.

```sh
# .env.local의 로컬 DATABASE_URL 사용, PATH에 도구가 없으면 PG_BIN 지정
PG_BIN=/Applications/Postgres.app/Contents/Versions/18/bin \
  simulation/.venv/bin/python scripts/verify_database_restore.py \
  --report tmp/restore-check-20261016.json
```

이 검사는 오프사이트 암호화 백업·WAL/PITR·MFA 암호화 키 복구·Oracle 성능 측정을 대체하지 않음. PostgreSQL의 논리 덤프는 한 DB만 포함하며 role·tablespace는 별도 관리. 운영용 백업은 실행 산출물·원본자료·고정 모델과 코드 버전을 포함한 암호화 사본 및 별도 키 보관 필요.

근거: [PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html). 임의 외부 덤프는 SQL 실행 위험으로 자동 복원하지 않음.

## 계산 캐시 운영

`docs/24-simulation-cache.md`의 비공개 전용 디렉터리·128개/2 GiB/7일 상한 적용. 캐시는 재계산 가능한 임시 자료, `data/runs`의 작업별 재현 산출물과 다른 볼륨 경로 사용. 캐시 삭제는 기존 작업·순위·동의·다운로드 권한을 바꾸지 않음. 비활성화/경로 변경은 워커 설정으로만 수행. 로컬 파일 잠금·원자적 게시 범위이며 NFS·다중 호스트 공유나 동시 미스 계산 병합은 지원하지 않음. 실제 Oracle에서 캐시 읽기/쓰기 시간·적중률·보관량·큐 지연 실측 필요.


## 리그 참가 PostgreSQL 통합 검사

`simulation/.venv/bin/python scripts/verify_league_postgres.py`는 `.env.local`을 값 출력 없이 읽고 로컬 PostgreSQL에 UUID 이름의 독립 시험 DB를 생성. Java 25의 실제 HTTP·MFA·CSRF·트랜잭션 시험 후 성공/실패와 관계없이 자신이 생성한 DB를 삭제. 로컬 시험 계정의 CREATEDB 권한 필요; 운영 서비스 계정에 해당 권한을 부여하는 배포 지침이 아님. 원본 계산·공개 제출·리그 수 변화 검사, 0600 로그 경로와 통과 여부만 출력. 과학 모델 검증이나 기존 원본 DB의 쓰기 시험이 아님.

CI도 별도 PostgreSQL 18.4 서비스 DB에서 같은 참가 통합 검사를 실행. CI의 공개 시험용 비밀번호는 서비스 컨테이너 전용이며 로컬·운영 비밀과 분리. 실제 Oracle 처리량·자원 제한은 별도 검증.
