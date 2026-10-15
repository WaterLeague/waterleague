import { expect, it } from 'vitest';
import { mapParticipation, mapParticipantPage } from './participationMapper';
const league = '10000000-0000-4000-8000-000000000001',
  owner = '10000000-0000-4000-8000-000000000002';
const person = () => ({
  leagueId: league,
  ownerId: owner,
  displayName: '시험 플레이어',
  state: 'APPROVED',
  revision: 1,
  reviewRequired: false,
  rulesHash: 'a'.repeat(64),
  createdAt: '2026-10-16T00:00:00Z',
  updatedAt: '2026-10-16T00:00:00Z',
});
const fixture = () => ({
  participant: person(),
  events: [],
  team: {
    id: '10000000-0000-4000-8000-000000000003',
    name: '시험 팀',
    captain: true,
    frozenAt: null,
    members: [{ displayName: '시험 플레이어', captain: true, self: true, eligible: true }],
    submissionCount: 2,
    eligible: true,
    invitationActive: true,
  },
  submissionCount: 2,
});
it('다른 회원 또는 다른 리그의 참가 응답 거부', () => {
  expect(mapParticipation(fixture(), league, owner).submissionCount).toBe(2);
  expect(() => mapParticipation(fixture(), owner, owner)).toThrow();
  expect(() => mapParticipation(fixture(), league, league)).toThrow();
});
it('팀 공유 횟수 불일치와 누락·중복 본인 구성 거부', () => {
  const count = fixture();
  count.team.submissionCount = 1;
  expect(() => mapParticipation(count, league, owner)).toThrow();
  const absent = fixture();
  absent.team.members[0].self = false;
  expect(() => mapParticipation(absent, league, owner)).toThrow();
  const duplicate = fixture();
  duplicate.team.members.push({ ...duplicate.team.members[0] });
  expect(() => mapParticipation(duplicate, league, owner)).toThrow();
  const noCaptain = fixture();
  noCaptain.team.members[0].captain = false;
  expect(() => mapParticipation(noCaptain, league, owner)).toThrow();
});
it('개인전과 참가 전 응답 허용, 회원 없는 팀 응답 거부', () => {
  expect(
    mapParticipation(
      { participant: null, events: [], team: null, submissionCount: 0 },
      league,
      owner
    ).participant
  ).toBeNull();
  expect(
    mapParticipation(
      { participant: person(), events: [], team: null, submissionCount: 1 },
      league,
      owner
    ).submissionCount
  ).toBe(1);
  expect(() => mapParticipation({ ...fixture(), participant: null }, league, owner)).toThrow();
});
it('신청 목록의 다른 리그·중복 회원·초과 페이지 거부', () => {
  const p = person();
  expect(mapParticipantPage({ items: [p], nextCursor: null }, league).items).toHaveLength(1);
  expect(() => mapParticipantPage({ items: [p], nextCursor: null }, owner)).toThrow();
  expect(() => mapParticipantPage({ items: [p, p], nextCursor: null }, league)).toThrow();
  expect(() =>
    mapParticipantPage({ items: Array(101).fill(p), nextCursor: null }, league)
  ).toThrow();
});
