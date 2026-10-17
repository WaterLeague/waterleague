import type { League } from '../entity/league';
import type { Participation, ParticipantState } from '../entity/participation';
export const participantNames: Record<ParticipantState, string> = {
  PENDING: '승인 대기',
  APPROVED: '참가 승인',
  REJECTED: '참가 반려',
  WITHDRAWN: '참가 철회',
};
export const validInvitation = (code: string) => /^[A-Za-z0-9_-]{43}$/.test(code);
export function canSubmit(
  league: Pick<League, 'phase'> & {
    rules: Pick<League['rules'], 'participation' | 'submissionLimit'>;
  },
  p: Participation | null
) {
  if (league.phase !== 'OPEN') return false;
  if (!league.rules.participation) return true;
  return (
    p?.participant?.state === 'APPROVED' &&
    p.submissionCount < league.rules.submissionLimit &&
    (league.rules.participation.entryMode === 'INDIVIDUAL' || !!p.team?.eligible)
  );
}
export const canRecruit = (l: League) => ['OPEN', 'SCHEDULED'].includes(l.phase);
