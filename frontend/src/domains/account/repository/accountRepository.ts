import { api, refreshCsrf } from '../../../shared/repository/apiClient';
import type { Account } from '../entity/account';
export const currentAccount = () => api<Account>('/auth/me');
export async function authenticate(
  mode: 'login' | 'register',
  username: string,
  password: string,
  otp?: string
) {
  await refreshCsrf();
  const account = await api<Account>('/auth/' + mode, 'POST', {
    username,
    password,
    ...(otp ? { otp } : {}),
  });
  await refreshCsrf();
  return account;
}
export async function logout() {
  await api('/auth/logout', 'POST', {});
  await refreshCsrf();
}
