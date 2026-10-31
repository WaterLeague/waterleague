import { expect, it } from 'vitest';
import { countInstallations, installationCountLabel } from './installationCounts';

it('응답 전과 조회 실패를 실제 0개와 구분한다', () => {
  expect(installationCountLabel(null, '11110')).toBe('시설 불러오는 중');
  expect(installationCountLabel(null, '11110', '연결 오류')).toBe('시설 확인 실패');
  expect(installationCountLabel({ '11110': 0 }, '11110')).toBe('시설 0개');
  expect(installationCountLabel({ '11110': 37 }, '11110', '갱신 지연')).toBe('시설 37개');
});

it('같은 위치의 다른 회원 시설도 각각 집계하고 빈 구는 0개로 표시한다', () => {
  const counts = countInstallations([
    { districtId: '11110' },
    { districtId: '11110' },
    { districtId: '11170' },
  ]);
  expect(installationCountLabel(counts, '11110')).toBe('시설 2개');
  expect(installationCountLabel(counts, '11170')).toBe('시설 1개');
  expect(installationCountLabel(counts, '11140')).toBe('시설 0개');
});
