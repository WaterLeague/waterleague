import { useEffect, useState } from 'react';
import { useAppLocation } from '../../../shared/controller/useAppLocation';
import { errorMessage } from '../../../shared/exception/ApiError';
import { loadCompetition, loadCompetitionResults } from '../repository/competitionRepository';
import type { Competition, CompetitionResults } from '../dto/competitionDto';
import type { FacilityType } from '../../game/entity/game';
export function useCompetitionGame(
  accountId: string | undefined,
  historical: boolean,
  eventId: string
) {
  const location = useAppLocation();
  const id = new URLSearchParams(location.split('?')[1] ?? '').get('competition');
  const [loaded, setLoaded] = useState<{ id: string; value: Competition } | null>(null),
    [error, setError] = useState('');
  const [results, setResults] = useState<CompetitionResults | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    setLoaded(null);
    setResults(null);
    setError('');
    if (!id) return;
    const abort = new AbortController();
    let fetching = false;
    const refresh = async () => {
      if (fetching || document.hidden) return;
      fetching = true;
      try {
        const value = await loadCompetition(id, abort.signal);
        if (!abort.signal.aborted) {
          setLoaded({ id, value });
          setError('');
        }
        if (value.joinedAt && value.mode === 'REALTIME') {
          const records = await loadCompetitionResults(id, 0, abort.signal);
          if (!abort.signal.aborted) setResults(records);
        }
      } catch (e) {
        if (!abort.signal.aborted) setError(errorMessage(e));
      } finally {
        fetching = false;
      }
    };
    void refresh();
    const poll = setInterval(() => void refresh(), 15000);
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      abort.abort();
      clearInterval(timer);
      clearInterval(poll);
    };
  }, [id, accountId]);
  const value = loaded?.id === id ? loaded.value : null;
  const ready =
    !!value &&
    !!value.joinedAt &&
    value.phase !== 'CANCELLED' &&
    now >= Date.parse(value.opensAt) &&
    now < Date.parse(value.closesAt) &&
    value.mode === (historical ? 'DISASTER' : 'REALTIME') &&
    (!historical || value.eventId === eventId);
  const permits = (district: string, type?: FacilityType) =>
    !id ||
    (ready &&
      !!value?.rules.districtIds.includes(district) &&
      (!type || value.rules.allowedTypes.includes(type)));
  return {
    id,
    value,
    ready,
    permits,
    own:
      results?.competition.id === id
        ? (results.groups
            .flatMap((g) => g.ownEntries ?? [])
            .find((r) => r.playerId === accountId) ?? null)
        : null,
    error: error || (id && value && !ready ? '대회 참가 여부와 개최 기간을 확인해 주세요.' : ''),
  };
}
