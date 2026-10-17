import { expect, it } from 'vitest';
import type { League } from '../entity/league';
import { mapLeague } from './leagueMapper';

function fixture(): League {
  return {
    id: '10000000-0000-4000-8000-000000000001',
    organizationId: '10000000-0000-4000-8000-000000000002',
    organizationName: '시험 기관',
    revision: 1,
    state: 'DRAFT',
    phase: 'DRAFT',
    title: '시험 리그',
    question: '규칙 검증',
    rulesHash: 'b'.repeat(64),
    executionHash: null,
    publishedAt: null,
    cancellationReason: null,
    playable: true,
    rules: {
      schemaVersion: 2,
      modelHash: 'a'.repeat(64),
      engineRevision: 'c'.repeat(40),
      generatorSha256: 'd'.repeat(64),
      scoreRule: 'ACCOUNTED_DISCHARGE_REDUCTION_V1',
      currency: 'KRW',
      budget: 300000000,
      allowedTypes: ['RAIN_GARDEN'],
      submissionLimit: 10,
      opensAt: '2026-10-16T00:00:00Z',
      closesAt: '2026-10-17T00:00:00Z',
      validationLevel: 'EXPLORATORY',
      official: false,
      placementLimit: 2,
      areaLimitM2: 40.03,
      award: { prizeKrw: 1000000, winnerCount: 2, notice: '로컬 시험 안내. 실제 지급 없음.' },
    },
  };
}

it('이전 규칙의 필드 부재와 해시를 유지하고 버전 2의 누락 필드 거부', () => {
  const current = fixture();
  expect(mapLeague(current).rules.areaLimitM2).toBe(40.03);
  const legacy = fixture();
  legacy.rules.schemaVersion = 1;
  delete legacy.rules.placementLimit;
  delete legacy.rules.areaLimitM2;
  delete legacy.rules.award;
  const mapped = mapLeague(legacy);
  expect(mapped.rulesHash).toBe(legacy.rulesHash);
  expect(mapped.rules).not.toHaveProperty('award');
  for (const field of ['placementLimit', 'areaLimitM2', 'award'] as const) {
    const invalid = fixture();
    delete invalid.rules[field];
    expect(() => mapLeague(invalid)).toThrow();
  }
});

it('면적 정밀도와 상금·수상 인원·안내 불일치 거부', () => {
  const area = fixture();
  area.rules.areaLimitM2 = 40.031;
  expect(() => mapLeague(area)).toThrow();
  for (const award of [
    { prizeKrw: 100, winnerCount: 0, notice: '선정 기준과 지급 일정 안내' },
    { prizeKrw: 0, winnerCount: 1, notice: '' },
    { prizeKrw: 100, winnerCount: 1, notice: '          ' },
    { prizeKrw: 0.5, winnerCount: 1, notice: '선정 기준과 지급 일정 안내' },
  ]) {
    const invalid = fixture();
    invalid.rules.award = award;
    expect(() => mapLeague(invalid)).toThrow();
  }
  const none = fixture();
  none.rules.award = { prizeKrw: 0, winnerCount: 0, notice: '' };
  expect(mapLeague(none).rules.award?.prizeKrw).toBe(0);
});

it('참가 규칙 버전과 팀 정원 일치 검사', () => {
  const l = fixture();
  l.rules.schemaVersion = 3;
  expect(() => mapLeague(l)).toThrow();
  l.rules.participation = {
    access: 'INVITE',
    admission: 'APPROVAL',
    entryMode: 'TEAM',
    teamSizeLimit: 4,
  };
  expect(mapLeague(l).rules.participation?.teamSizeLimit).toBe(4);
  l.rules.participation.teamSizeLimit = null;
  expect(() => mapLeague(l)).toThrow();
  l.rules.participation.entryMode = 'INDIVIDUAL';
  expect(mapLeague(l).rules.participation?.entryMode).toBe('INDIVIDUAL');
  l.rules.participation.teamSizeLimit = 2;
  expect(() => mapLeague(l)).toThrow();
  l.rules.schemaVersion = 2;
  expect(() => mapLeague(l)).toThrow();
});
