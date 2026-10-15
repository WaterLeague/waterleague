import { expect, it } from 'vitest';
import { canSubmit, validInvitation } from './participationService';
import type { LeagueParticipationRules } from '../entity/league';
import type { Participation } from '../entity/participation';
const rules: LeagueParticipationRules = {
  access: 'INVITE',
  admission: 'APPROVAL',
  entryMode: 'TEAM',
  teamSizeLimit: 4,
};
const league = { phase: 'OPEN' as const, rules: { participation: rules, submissionLimit: 2 } };
const p = (): Participation => ({
  participant: {
    leagueId: 'l',
    ownerId: 'o',
    displayName: '시험',
    state: 'APPROVED',
    revision: 1,
    reviewRequired: false,
    rulesHash: 'h',
    createdAt: '',
    updatedAt: '',
  },
  events: [],
  team: {
    id: 't',
    name: '팀',
    captain: false,
    frozenAt: null,
    members: [],
    submissionCount: 1,
    eligible: true,
    invitationActive: false,
  },
  submissionCount: 1,
});
it('승인·팀 소속·팀 적격·공유 한도를 모두 충족할 때만 제출 허용', () => {
  expect(canSubmit(league, p())).toBe(true);
  expect(canSubmit(league, null)).toBe(false);
  const waiting = p();
  waiting.participant!.state = 'PENDING';
  expect(canSubmit(league, waiting)).toBe(false);
  const noTeam = p();
  noTeam.team = null;
  expect(canSubmit(league, noTeam)).toBe(false);
  const suspended = p();
  suspended.team!.eligible = false;
  expect(canSubmit(league, suspended)).toBe(false);
  const exhausted = p();
  exhausted.submissionCount = 2;
  expect(canSubmit(league, exhausted)).toBe(false);
});
it('개인전과 이전 규칙 유지, 마감·취소·예정 제출 차단', () => {
  const individual = p();
  individual.team = null;
  expect(
    canSubmit(
      {
        ...league,
        rules: {
          ...league.rules,
          participation: { ...rules, entryMode: 'INDIVIDUAL', teamSizeLimit: null },
        },
      },
      individual
    )
  ).toBe(true);
  expect(canSubmit({ phase: 'OPEN', rules: { submissionLimit: 2 } }, null)).toBe(true);
  for (const phase of ['CLOSED', 'CANCELLED', 'SCHEDULED', 'DRAFT'] as const)
    expect(canSubmit({ ...league, phase }, p())).toBe(false);
});
it('초대 코드 길이·문자 검증과 URL·여백 거부', () => {
  expect(validInvitation('a'.repeat(43))).toBe(true);
  for (const code of [
    '',
    'a'.repeat(42),
    'a'.repeat(44),
    ' '.repeat(43),
    'https://example.com/?code=' + 'a'.repeat(43),
  ])
    expect(validInvitation(code)).toBe(false);
});
