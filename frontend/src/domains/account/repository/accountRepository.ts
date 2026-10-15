import { api, refreshCsrf } from '../../../shared/repository/apiClient';
import type { Account, MemberType } from '../entity/account';
export const currentAccount = () => api<Account>('/auth/me');
export async function authenticate(
  mode: 'login' | 'register',
  username: string,
  password: string,
  otp?: string,
  registration?: { memberType: MemberType; organizationName: string; purpose: string }
) {
  await refreshCsrf();
  const account = await api<Account>('/auth/' + mode, 'POST', {
    username,
    password,
    ...(mode === 'register' ? registration : otp ? { otp } : {}),
  });
  await refreshCsrf();
  return account;
}
export async function logout() {
  await api('/auth/logout', 'POST', {});
  await refreshCsrf();
}

export async function beginEnrollment(username: string, password: string) {
  await refreshCsrf();
  const enrollment = await api<{
    secret: string;
    issuer: string;
    accountName: string;
    expiresInSeconds: number;
  }>('/auth/mfa/enrollment', 'POST', { username, password });
  await refreshCsrf();
  return enrollment;
}
export async function confirmEnrollment(otp: string) {
  const account = await api<Account>('/auth/mfa/confirm', 'POST', { otp });
  await refreshCsrf();
  return account;
}
