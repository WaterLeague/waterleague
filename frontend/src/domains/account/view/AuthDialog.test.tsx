import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AuthDialog } from './AuthDialog';

test('일반 로그인은 아이디·비밀번호만 표시하고 관리자 확인 전 OTP를 요구하지 않음', () => {
  const html = renderToStaticMarkup(<AuthDialog onClose={() => {}} onSuccess={() => {}} />);
  expect(html).toContain('autoComplete="username"');
  expect(html).toContain('autoComplete="current-password"');
  expect(html).not.toContain('one-time-code');
  expect(html).not.toContain('인증 앱 번호');
  expect(html).toContain('minLength="8"');
});
