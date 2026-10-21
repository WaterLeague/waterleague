-- 관리자 이외 계정의 사용하지 않는 인증 앱 비밀 제거.
DELETE FROM account_mfa
WHERE account_id IN (SELECT id FROM accounts WHERE role <> 'ADMIN');
