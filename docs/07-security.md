# 보안·권한

인증·인가·입력·격리·공급망·운영의 검증 가능한 통제 적용. 완전한 보안이라는 선언보다 테스트·운영 증거로 관리.

## 인증·요청

서버 세션·프레임워크 사용. 운영 쿠키 __Host- 접두사, Secure·HttpOnly·SameSite=Lax·Path=/·Domain 미설정. 로그인·권한 변경 시 세션 회전, 유휴·절대 만료, 서버 로그아웃. 토큰 localStorage 저장 금지. [OWASP 세션 지침](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) 참고.

Argon2id 최소 m=19MiB·t=2·p=1에서 성능 측정·상향. 비밀번호 길이 12~128자, 인증 실패 메시지 일반화, 가입·로그인·복구 rate limit. 이메일 검증·재설정·유출 비밀번호 검사·기관 MFA/IdP는 공개 운영 전 게이트. [OWASP 비밀번호 지침](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) 참고.

상태 변경 CSRF 검사, SameSite만으로 대체 금지. 동일 출처 기본, wildcard CORS+credentials 금지. HTTPS·운영 HSTS·CSP·frame-ancestors none·nosniff·Referrer-Policy. 개발 HMR 예외를 운영에 복사 금지. DTO 검증·과대 본문·unknown field·비유한 수 거부, 매개변수 쿼리·sort allowlist, HTML 원문 렌더링 금지.

## 객체 권한

소유자·기관 소속·리그 소유·동의 범위 매 요청 검증. URL ID나 클라이언트 role 불신. 가입은 PLAYER 고정. 기관 관리자의 모델 승인·플랫폼 권한 부여 금지. 권한 철회 시 세션·캐시 무효화. export 다운로드에도 동의 재검사.

## 계산·수집

외부 INP·Python·셸·임의 URL 실행 금지. 승인된 모델, 서버 생성 UUID 경로. 워커 비root·read-only rootfs·작업 임시 공간·CPU/메모리/시간/결과크기 제한, 자식 process group 종료. lease·재시도 상한·fencing token·해시 검증. 사용자 쿼터·큐 상한·역압·중복 캐시.

데이터 수집 allowlist·TLS·크기·timeout·구조 검사. export 경로 순회·CSV formula injection·민감 필드 검사.

## 운영

비밀키 환경/secret mount, 저장소·이미지·브라우저 제외. DB·워커 외부 포트 미노출, 앱·migration·백업 계정 분리. 의존성 고정·취약점·SBOM·secret 검사, CI 최소 권한·action SHA 고정. 암호화 백업·복원 훈련. TLS·메일·기관 인증·보존정책 확인 전 공개 회원 서비스 배포 금지.

기관 열람·export·권한 변경·모델 승인·공식 제출 감사. 비밀번호·세션·API키·전략 원문 일반 로그 금지. 연구에는 익명 식별자와 필요한 필드만 제공.

## 검증

다른 사용자 전략, 다른 기관 자료, 철회 후 접근, 역할 주입 가입, CSRF 누락, 경로 순회, 초과 배치·예산·NaN, 제출 한도 경합, 멱등키 충돌, 만료 워커, 미승인 모델 공식 제출 검사. 정상 흐름만으로 보안 완료 판정 금지.
