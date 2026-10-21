import { useEffect, useState } from 'react';
import { useAppLocation } from '../../../shared/controller/useAppLocation';
import { errorMessage } from '../../../shared/exception/ApiError';
import { loadCompetition } from '../repository/competitionRepository';
import type { Competition } from '../dto/competitionDto';
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
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    setLoaded(null);
    setError('');
    if (!id) return;
    const abort = new AbortController();
    void loadCompetition(id, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setLoaded({ id, value });
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(errorMessage(e));
      });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [id, accountId]);
  const value = loaded?.id === id ? loaded.value : null;
  const ready =
    !!value &&
    !!value.joinedAt &&
    value.phase === 'OPEN' &&
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
    error: error || (id && value && !ready ? '대회 참가 여부와 개최 기간을 확인해 주세요.' : ''),
  };
}
