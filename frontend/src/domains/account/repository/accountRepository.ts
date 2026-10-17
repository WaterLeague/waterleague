import { api, refreshCsrf, resetSessionToken } from '../../../shared/repository/apiClient';
import { ApiError } from '../../../shared/exception/ApiError';
import type { Account, MemberType } from '../entity/account';
export const currentAccount = () => api<Account>('/auth/me');
export async function authenticate(
  mode: 'login' | 'register',
  username: string,
  password: string,
  otp?: string,
  registration?: {
    memberType: MemberType;
    organizationName: string;
    purpose: string;
    districtId: string;
    affiliationType: 'RESIDENT' | 'AFFILIATED';
  }
) {
  resetSessionToken();
  await refreshCsrf();
  const account = await api<Account>('/auth/' + mode, 'POST', {
    username,
    password,
    ...(mode === 'register' ? registration : otp ? { otp } : {}),
  });
  resetSessionToken();
  return account;
}
export async function logout() {
  resetSessionToken();
  await refreshCsrf();
  try {
    await api('/auth/logout', 'POST', {});
  } catch (error) {
    if (!(error instanceof ApiError && error.code === 'AUTHENTICATION_REQUIRED')) throw error;
  }
  resetSessionToken();
}

export async function beginEnrollment(username: string, password: string) {
  resetSessionToken();
  await refreshCsrf();
  const enrollment = await api<{
    secret: string;
    issuer: string;
    accountName: string;
    expiresInSeconds: number;
  }>('/auth/mfa/enrollment', 'POST', { username, password });
  resetSessionToken();
  return enrollment;
}
export async function confirmEnrollment(otp: string) {
  const account = await api<Account>('/auth/mfa/confirm', 'POST', { otp });
  resetSessionToken();
  return account;
}

export const selectAccountDistrict = (
  districtId: string,
  affiliationType: 'RESIDENT' | 'AFFILIATED'
) => api<Account>('/auth/district', 'POST', { districtId, affiliationType });
