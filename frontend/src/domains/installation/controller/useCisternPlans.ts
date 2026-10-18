import { useCallback, useEffect, useRef, useState } from 'react';
import type { Account } from '../../account/entity/account';
import type { SharedSite } from '../entity/installation';
import type { CisternPlan } from '../dto/cisternPlanDto';
import {
  cisternRequest,
  cisternSelectionError,
  type CisternSiteRole,
} from '../service/cisternPlanService';
import {
  deleteCisternPlan,
  loadCisternPlans,
  saveCisternPlan,
} from '../repository/cisternPlanRepository';
import { errorMessage } from '../../../shared/exception/ApiError';

export function useCisternPlans(account: Account | null, open: boolean) {
  const allowed = account?.role === 'MEMBER' && account.approvalStatus === 'APPROVED';
  const identity = account
    ? `${account.id}:${account.role}:${account.approvalStatus}:${account.districtId ?? ''}`
    : 'visitor';
  const [scope, setScope] = useState(identity);
  const [role, setRole] = useState<CisternSiteRole>('roof');
  const [roof, setRoof] = useState<SharedSite | null>(null),
    [ground, setGround] = useState<SharedSite | null>(null);
  const [capture, setCapture] = useState(''),
    [area, setArea] = useState(''),
    [depth, setDepth] = useState('');
  const [plans, setPlans] = useState<CisternPlan[]>([]),
    [saved, setSaved] = useState<CisternPlan | null>(null);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const epoch = useRef(0),
    posting = useRef<AbortController | null>(null);
  useEffect(() => {
    epoch.current++;
    posting.current?.abort();
    posting.current = null;
    setPlans([]);
    setSaved(null);
    setRoof(null);
    setGround(null);
    setCapture('');
    setArea('');
    setDepth('');
    setRole('roof');
    setError('');
    setBusy(false);
    setLoading(false);
    setScope(identity);
    return () => {
      epoch.current++;
      posting.current?.abort();
    };
  }, [identity]);
  useEffect(() => {
    if (!open || !allowed) return;
    const abort = new AbortController(),
      current = epoch.current;
    setLoading(true);
    void loadCisternPlans(abort.signal)
      .then((values) => {
        if (!abort.signal.aborted && current === epoch.current) {
          setPlans(values);
          setError('');
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted && current === epoch.current) setError(errorMessage(e));
      })
      .finally(() => {
        if (!abort.signal.aborted && current === epoch.current) setLoading(false);
      });
    return () => abort.abort();
  }, [open, allowed, identity, revision]);
  const select = useCallback(
    (site: SharedSite, occupied: boolean) => {
      const message = cisternSelectionError(site, role, account?.districtId ?? null, occupied);
      if (message) {
        setError(message);
        return false;
      }
      if (role === 'ground' && roof && roof.districtId !== site.districtId) {
        setError('집수 지붕과 같은 구의 지상 후보를 선택해 주세요.');
        return false;
      }
      setError('');
      setSaved(null);
      if (role === 'roof') {
        setRoof(site);
        setCapture(String(site.maxAreaM2));
        if (ground?.districtId !== site.districtId) setGround(null);
        setRole('ground');
      } else setGround(site);
      return true;
    },
    [role, account?.districtId, roof?.districtId, ground?.districtId]
  );
  function restore(plan: CisternPlan) {
    const s = plan.snapshot;
    setRoof(s.roof);
    setGround(s.ground);
    setCapture(String(s.request.captureAreaM2));
    setArea(String(s.request.tankAreaM2));
    setDepth(String(s.request.tankDepthM));
    setSaved(plan);
    setRole('ground');
    setError('');
  }
  function edit(key: 'capture' | 'area' | 'depth', value: string) {
    setSaved(null);
    ({ capture: setCapture, area: setArea, depth: setDepth })[key](value);
  }
  const currentScope = scope === identity;
  const request = currentScope ? cisternRequest(roof, ground, capture, area, depth) : null;
  async function mutate(remove?: CisternPlan) {
    if (!allowed || posting.current || (!remove && !request)) return;
    const abort = new AbortController(),
      current = epoch.current;
    posting.current = abort;
    setBusy(true);
    setError('');
    try {
      if (remove) await deleteCisternPlan(remove.id, abort.signal);
      else {
        const next = await saveCisternPlan(request!, abort.signal);
        if (!abort.signal.aborted && current === epoch.current) setSaved(next);
      }
      if (!abort.signal.aborted && current === epoch.current) {
        if (remove?.id === saved?.id) setSaved(null);
        setRevision((v) => v + 1);
      }
    } catch (e) {
      if (!abort.signal.aborted && current === epoch.current) setError(errorMessage(e));
    } finally {
      if (current === epoch.current) {
        setBusy(false);
        posting.current = null;
      }
    }
  }
  return {
    allowed,
    role,
    setRole,
    roof: currentScope ? roof : null,
    ground: currentScope ? ground : null,
    capture: currentScope ? capture : '',
    area: currentScope ? area : '',
    depth: currentScope ? depth : '',
    edit,
    plans: currentScope ? plans : [],
    saved: currentScope ? saved : null,
    error,
    busy,
    loading,
    select,
    restore,
    valid: !!request,
    save: () => mutate(),
    remove: (plan: CisternPlan) => mutate(plan),
    retry: () => setRevision((v) => v + 1),
  };
}
export type CisternPlanState = ReturnType<typeof useCisternPlans>;
