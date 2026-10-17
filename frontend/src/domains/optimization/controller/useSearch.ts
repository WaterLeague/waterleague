import { useEffect, useRef, useState } from 'react';
import type { Lab } from '../../game/entity/game';
import type { SearchInput } from '../entity/search';
import { SearchSession, emptySearchState } from '../service/SearchSession';
import { searchRepository } from '../repository/searchRepository';
import { searchActive } from '../service/searchService';
export function useSearch(lab: Lab, organizationId: string) {
  const [state, setState] = useState(emptySearchState),
    session = useRef<SearchSession | null>(null);
  useEffect(() => {
    const c = new SearchSession(searchRepository(lab, organizationId), setState);
    session.current = c;
    setState(emptySearchState());
    void c.refresh();
    const refresh = () => void c.refresh(true),
      visibility = () => {
        if (document.visibilityState === 'visible') refresh();
        else c.conceal();
      };
    const timer = window.setInterval(() => {
      if (
        document.visibilityState === 'visible' &&
        Date.now() - c.lastRefresh >= (searchActive(c.state.detail) ? 2000 : 30000)
      )
        void c.refresh();
    }, 2000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      c.dispose();
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', visibility);
      if (session.current === c) session.current = null;
    };
  }, [lab, organizationId]);
  return {
    ...state,
    create: (input: SearchInput) => void session.current?.create(input),
    open: (id: string) => void session.current?.open(id),
    invalidate: () => session.current?.invalidate(),
    refresh: () => void session.current?.refresh(true),
  };
}
