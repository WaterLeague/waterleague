import { useEffect, useRef, useState } from 'react';
import { ApiError, errorMessage } from '../../../shared/exception/ApiError';
import type { HistoricalDraft } from '../entity/historical';
import {
  designItems,
  loadDesign,
  restoreDesign,
  saveDesign,
  type DesignRequest,
} from '../repository/designRepository';
type State = {
  key: string;
  drafts: HistoricalDraft[];
  revision: number;
  snapshotSha256: string | null;
  loaded: boolean;
  saving: boolean;
  error: string;
  conflict: boolean;
  pending: DesignRequest | null;
  restoredSecond: number;
  restoreId: number;
};
export function useHistoricalDesign(enabled: boolean, eventId: string, ownerId?: string) {
  const key = `${ownerId ?? 'guest'}/${eventId}`;
  const [state, setState] = useState<State | null>(null);
  const latest = useRef(state);
  latest.current = state;
  const [refresh, setRefresh] = useState(0);
  const guests = useRef(new Map<string, { drafts: HistoricalDraft[]; second: number }>());
  const inFlight = useRef(new Map<string, Promise<void>>());
  const sequence = useRef(0);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const restoreId = ++sequence.current;
    const initial: State = {
      key,
      drafts: [],
      revision: 0,
      snapshotSha256: null,
      loaded: false,
      saving: false,
      error: '',
      conflict: false,
      pending: null,
      restoredSecond: 0,
      restoreId,
    };
    setState(initial);
    void (async () => {
      try {
        await inFlight.current.get(key);
        if (!ownerId) {
          const guest = guests.current.get(eventId);
          if (active)
            setState({
              ...initial,
              loaded: true,
              drafts: guest?.drafts ?? [],
              restoredSecond: guest?.second ?? 0,
            });
          return;
        }
        const value = await loadDesign(eventId);
        if (active)
          setState({
            ...initial,
            loaded: true,
            drafts: restoreDesign(value, ownerId),
            revision: value.revision,
            snapshotSha256: value.snapshotSha256,
            restoredSecond: value.snapshot?.elapsedSeconds ?? 0,
          });
      } catch (e) {
        if (active) setState({ ...initial, error: errorMessage(e) });
      }
    })();
    return () => {
      active = false;
    };
  }, [enabled, key, refresh]);
  const current = enabled && state?.key === key ? state : null;
  useEffect(() => {
    if (!current?.saving && !current?.pending) return;
    const leave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', leave);
    return () => window.removeEventListener('beforeunload', leave);
  }, [current?.saving, current?.pending]);
  function send(request: DesignRequest) {
    if (!ownerId || latest.current?.key !== key || inFlight.current.has(key)) return;
    const restoreId = latest.current.restoreId;
    setState((s) => (s?.key === key ? { ...s, saving: true, pending: request, error: '' } : s));
    const operation = (async () => {
      try {
        const saved = await saveDesign(eventId, request);
        const drafts = restoreDesign(saved, ownerId);
        setState((s) =>
          s?.key === key && s.restoreId === restoreId
            ? {
                ...s,
                drafts,
                revision: saved.revision,
                snapshotSha256: saved.snapshotSha256,
                saving: false,
                pending: null,
                error: '',
                conflict: false,
              }
            : s
        );
      } catch (e) {
        setState((s) =>
          s?.key === key && s.restoreId === restoreId
            ? {
                ...s,
                saving: false,
                error: errorMessage(e),
                conflict: e instanceof ApiError && e.status === 409,
              }
            : s
        );
      } finally {
        inFlight.current.delete(key);
      }
    })();
    inFlight.current.set(key, operation);
  }
  function replace(drafts: HistoricalDraft[], elapsedSeconds: number) {
    const current = latest.current;
    if (!enabled || current?.key !== key || !current.loaded || current.saving || current.pending)
      return;
    if (!ownerId) {
      guests.current.set(eventId, { drafts, second: elapsedSeconds });
      setState({ ...current, drafts });
      return;
    }
    send({
      requestKey: crypto.randomUUID(),
      baseRevision: current.revision,
      elapsedSeconds,
      placements: designItems(drafts),
    });
  }
  return {
    drafts: current?.drafts ?? [],
    revision: current?.revision ?? 0,
    snapshotSha256: current?.snapshotSha256 ?? null,
    ready: !!current?.loaded && !current.saving && !current.pending,
    loading: enabled && !current?.loaded,
    saving: current?.saving ?? false,
    error: current?.error ?? '',
    conflict: current?.conflict ?? false,
    restoredSecond: current?.restoredSecond ?? 0,
    restoreId: current?.loaded ? current.restoreId : 0,
    replace,
    reload: () => setRefresh((v) => v + 1),
    retry: () => {
      if (current?.pending && !current.conflict) send(current.pending);
      else setRefresh((v) => v + 1);
    },
    guestCount: ownerId ? (guests.current.get(eventId)?.drafts.length ?? 0) : 0,
    importGuest: () => {
      const guest = guests.current.get(eventId);
      if (guest) replace(guest.drafts, guest.second);
    },
  };
}
