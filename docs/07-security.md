# 보안·권한

인증·인가·입력·격리·공급망·운영의 검증 가능한 통제 적용. 완전한 보안이라는 선언보다 테스트·운영 증거로 관리.

## 인증·요청

서버 세션·프레임워크 사용. 운영 쿠키 __Host- 접두사, Secure·HttpOnly·SameSite=Lax·Path=/·Domain 미설정. 로그인·권한 변경 시 세션 회전, 유휴·절대 만료, 서버 로그아웃. 토큰 localStorage 저장 금지. [OWASP 세션 지침](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) 참고.

Argon2id 최소 m=19MiB·t=2·p=1에서 성능 측정·상향. 비밀번호 길이 8~128자(2026-10-17 사용자 요청: 최소 8자). 회원가입 폼의 비밀번호 확인란 필수·불일치 제출 차단, 확인값의 서버 전송·저장 없음. 인증 실패 메시지 일반화, 가입·로그인·복구 rate limit. 이메일 검증·재설정·유출 비밀번호 검사·기관 MFA/IdP는 공개 운영 전 게이트. [OWASP 비밀번호 지침](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) 참고.

기관 인증 구현: [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238) TOTP 6자리·30초·인접 1구간 허용, 사용 카운터 조건부 갱신으로 재사용 거부. 기관별 비밀은 계정 ID를 AAD로 한 AES-256-GCM 암호화 저장, `MFA_ENCRYPTION_KEY`는 DB와 분리. 키·등록 정보 부재 시 기관 로그인 거부. 공개 가입에서 등록·역할 변경 불가, 로컬 운영 명령에서 소속 확인 후 기존 계정 승격. 기관 MFA는 피싱 저항성을 제공하지 않으므로 운영 IdP/WebAuthn 도입 전 위험 검토 필요.

로그인 세션 절대 만료 8시간, 유휴 만료 30분. 매 요청 계정 활성 상태·현재 역할·기관 MFA 확인. 권한 변경·재등록 시 기존 세션 삭제. JSON 본문 64 KiB 상한, 전역 작업 입장 잠금으로 큐 상한 경합 차단.

상태 변경 CSRF 검사, SameSite만으로 대체 금지. 동일 출처 기본, wildcard CORS+credentials 금지. HTTPS·운영 HSTS·CSP·frame-ancestors none·nosniff·Referrer-Policy. 개발 HMR 예외를 운영에 복사 금지. DTO 검증·과대 본문·unknown field·비유한 수 거부, 매개변수 쿼리·sort allowlist, HTML 원문 렌더링 금지.

## 객체 권한

소유자·기관 소속·리그 소유·동의 범위 매 요청 검증. URL ID나 클라이언트 role 불신. 가입은 MEMBER 역할 고정. PLAYER는 즉시 승인, BUSINESS·INSTITUTION·GOVERNMENT는 관리자 승인 전 이용 차단. ADMIN은 DB 유일 제약으로 한 계정만 허용하며 조직 회원과 분리. 회원의 모델 승인·플랫폼 권한 부여 금지. 권한 철회 시 세션·캐시 무효화. export 다운로드에도 동의 재검사.

사업 활용 검토는 계산·기관·목적 hash와 정책 버전에 묶인 별도 소유자 동의. 요청 상태와 결정 이벤트 원자적 저장, 예상 revision·내용 hash 불일치 거부. 연구 동의를 철회해도 별도로 승인한 사업 동의는 유지되므로 각 활성 동의의 관리 화면 제공. [상태·검증 계약](17-utilization-consent.md) 참조.

## 계산·수집

외부 INP·Python·셸·임의 URL 실행 금지. 승인된 모델, 서버 생성 UUID 경로. 워커 비root·read-only rootfs·작업 임시 공간·CPU/메모리/시간/결과크기 제한, 자식 process group 종료. lease·재시도 상한·fencing token·해시 검증. 사용자 쿼터·큐 상한·역압·중복 캐시.

데이터 수집 allowlist·TLS·크기·timeout·구조 검사. export 경로 순회·CSV formula injection·민감 필드 검사.

## 운영

비밀키 환경/secret mount, 저장소·이미지·브라우저 제외. DB·워커 외부 포트 미노출, 앱·migration·백업 계정 분리. 의존성 고정·취약점·SBOM·secret 검사, CI 최소 권한·action SHA 고정. 암호화 백업·복원 훈련. TLS·메일·기관 인증·보존정책 확인 전 공개 회원 서비스 배포 금지.

기관 열람·export·권한 변경·모델 승인·공식 제출 감사. 비밀번호·세션·API키·전략 원문 일반 로그 금지. 연구에는 익명 식별자와 필요한 필드만 제공.

## 검증

다른 사용자 전략, 다른 기관 자료, 철회 후 접근, 역할 주입 가입, CSRF 누락, 경로 순회, 초과 배치·예산·NaN, 제출 한도 경합, 멱등키 충돌, 만료 워커, 미승인 모델 공식 제출 검사. 정상 흐름만으로 보안 완료 판정 금지.

2026-10-19 게스트 결과 경계: 최종 점수 잠금은 화면뿐 아니라 서버 응답에도 적용. 개별 조회·목록·동일 요청 재응답에서 전체 기간 합계·최종 구간·시설별 전체 기간 비교 제거. 게스트 세션 소유권·CSRF·입장 제한·회원 주간 설치 차단 유지. 원 계산과 재현 자료는 변경하지 않음.

## 도시 공개 화면 수집 (2026-10-19)

서버 고정 `https://data.seoul.go.kr/SeoulRtd/` 호스트와 두 서비스 이름만 사용한다. 브라우저는 자체 API만 호출하며 외부 인증키·사용자 쿠키를 전송하지 않는다. 일반 공개 페이지 Referer를 사용하되 TLS 인증서 검증·리디렉션 차단·Content-Type·크기·타임아웃을 유지한다. 입력 장소는 프로젝트에 고정한 카탈로그 해시로 검증한 이름으로 변환하며 사용자 URL/장소명을 외부 주소에 직접 연결하지 않는다. 원문 HTML·예보/과거 값·잘못된 시각·비유한 값·장소 불일치는 현재 관측으로 승격하지 않는다. `.env.local`의 `SEOUL_OPEN_DATA_KEY`는 프론트/워커 프로세스 상속에서 제거하며 이번 공개 HTTPS 경로는 키를 사용하지 않는다. 비암호화 HTTP API에 키를 보내는 대체 경로 없음.
