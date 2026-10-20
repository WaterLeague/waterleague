import type { CisternSpecification } from '../../facility/dto/cisternSpecificationDto';
import { loadCisternSpecifications } from '../../facility/repository/cisternSpecificationRepository';
import { cisternEquipmentPlanRequest } from '../service/cisternPlanService';
import { cisternEquipmentGeometry, parseCisternEquipment } from '../service/cisternLayoutService';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Account } from '../../account/entity/account';
import type { SharedSite } from '../entity/installation';
import type { CisternPlan, CisternPlanMode } from '../dto/cisternPlanDto';
import {
  cisternRequest,
  cisternPlanRequestForMode,
  cisternSelectionError,
  type CisternSiteRole,
} from '../service/cisternPlanService';
import {
  deleteCisternPlan,
  loadCisternPlans,
  saveCisternPlan,
} from '../repository/cisternPlanRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
import {
  cisternGeometry,
  parseCisternLayout,
  type CisternLayoutFields,
} from '../service/cisternLayoutService';
const emptyLayout: CisternLayoutFields = {
  width: '',
  wall: '',
  east: '0',
  north: '0',
  rotation: '0',
};

export function useCisternPlans(
  account: Account | null,
  open: boolean,
  mode: CisternPlanMode,
  onInstalled?: (site: SharedSite) => void
) {
  const allowed = account?.role === 'MEMBER' && account.approvalStatus === 'APPROVED';
  const identity = account
    ? `${account.id}:${account.role}:${account.approvalStatus}:${account.districtId ?? ''}:${mode}`
    : `visitor:${mode}`;
  const latestIdentity = useRef(identity);
  latestIdentity.current = identity;
  const [specifications, setSpecifications] = useState<CisternSpecification[]>([]);
  const [specificationId, setSpecificationId] = useState('');
  const [specificationError, setSpecificationError] = useState('');
  const [specificationsLoading, setSpecificationsLoading] = useState(false);
  const [scope, setScope] = useState(identity);
  const [role, setRole] = useState<CisternSiteRole>('roof');
  const [roof, setRoof] = useState<SharedSite | null>(null),
    [ground, setGround] = useState<SharedSite | null>(null);
  const [capture, setCapture] = useState(''),
    [area, setArea] = useState(''),
    [depth, setDepth] = useState('');
  const [layoutFields, setLayoutFields] = useState<CisternLayoutFields>(emptyLayout);
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
    setLayoutFields(emptyLayout);
    setSpecificationId('');
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
        if (
          !abort.signal.aborted &&
          current === epoch.current &&
          latestIdentity.current === identity
        ) {
          setPlans(values);
          setError('');
        }
      })
      .catch((e) => {
        if (
          !abort.signal.aborted &&
          current === epoch.current &&
          latestIdentity.current === identity
        )
          setError(errorMessage(e));
      })
      .finally(() => {
        if (
          !abort.signal.aborted &&
          current === epoch.current &&
          latestIdentity.current === identity
        )
          setLoading(false);
      });
    return () => abort.abort();
  }, [open, allowed, identity, revision]);
  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    setSpecificationsLoading(true);
    void loadCisternSpecifications(abort.signal)
      .then((catalog) => {
        if (!abort.signal.aborted) {
          setSpecifications(catalog.specifications);
          setSpecificationError('');
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setSpecifications([]);
          setSpecificationError(errorMessage(e));
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setSpecificationsLoading(false);
      });
    return () => abort.abort();
  }, [open, revision]);
  const select = useCallback(
    (site: SharedSite, occupied: boolean) => {
      const message = cisternSelectionError(
        site,
        role,
        account?.districtId ?? null,
        occupied,
        mode
      );
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
      } else {
        setGround(site);
        if (ground?.cellId !== site.cellId)
          setLayoutFields((v) => ({ ...v, east: '0', north: '0', rotation: '0' }));
      }
      return true;
    },
    [role, account?.districtId, roof?.districtId, ground?.districtId, ground?.cellId, mode]
  );
  function restore(plan: CisternPlan) {
    const s = plan.snapshot;
    const invalid =
      cisternSelectionError(s.roof, 'roof', account?.districtId ?? null, false, mode) ||
      cisternSelectionError(s.ground, 'ground', account?.districtId ?? null, false, mode);
    if (invalid) {
      setError(invalid);
      return false;
    }
    setRoof(s.roof);
    setGround(s.ground);
    setCapture(String(s.request.captureAreaM2));
    setArea(s.request.tankAreaM2 === null ? '' : String(s.request.tankAreaM2));
    setDepth(s.request.tankDepthM === null ? '' : String(s.request.tankDepthM));
    setSpecificationId(s.request.equipment?.specificationId ?? '');
    const l = s.request.tankLayout;
    setLayoutFields(
      l
        ? {
            width: String(l.widthM),
            wall: String(l.wallThicknessM),
            east: String(l.offsetXM),
            north: String(l.offsetYM),
            rotation: String(l.rotationDeg),
          }
        : emptyLayout
    );
    if (s.request.equipment) {
      const e = s.request.equipment;
      setLayoutFields({
        ...emptyLayout,
        east: String(e.offsetXM),
        north: String(e.offsetYM),
        rotation: String(e.rotationDeg),
      });
    }
    setSaved(plan);
    setRole('ground');
    setError('');
    return true;
  }
  function edit(key: 'capture' | 'area' | 'depth', value: string) {
    setSaved(null);
    ({ capture: setCapture, area: setArea, depth: setDepth })[key](value);
  }
  const currentScope = scope === identity;
  const layout = useMemo(() => parseCisternLayout(layoutFields), [layoutFields]);
  const manualGeometry = useMemo(
    () =>
      currentScope && ground && layout
        ? cisternGeometry(ground, Number(area), Number(depth), layout)
        : null,
    [currentScope, ground, layout, area, depth]
  );
  const specification = currentScope
    ? (specifications.find((v) => v.id === specificationId) ?? null)
    : null;
  const equipment = useMemo(
    () => (specification ? parseCisternEquipment(layoutFields, specification.id) : null),
    [layoutFields, specification]
  );
  const equipmentGeometry = useMemo(
    () =>
      currentScope && ground && specification && equipment
        ? cisternEquipmentGeometry(ground, specification, equipment)
        : null,
    [currentScope, ground, specification, equipment]
  );
  const geometry = specificationId ? equipmentGeometry : manualGeometry;
  const baseRequest = currentScope ? cisternRequest(roof, ground, capture, area, depth) : null;
  const geometryRequest = specificationId
    ? specification && equipment && equipmentGeometry?.contained
      ? cisternEquipmentPlanRequest(roof, ground, capture, equipment, specification)
      : null
    : baseRequest && manualGeometry?.contained && layout
      ? { ...baseRequest, tankLayout: layout }
      : null;
  const selectionValid =
    roof &&
    ground &&
    !cisternSelectionError(roof, 'roof', account?.districtId ?? null, false, mode) &&
    !cisternSelectionError(ground, 'ground', account?.districtId ?? null, false, mode);
  const request = cisternPlanRequestForMode(
    selectionValid ? geometryRequest : null,
    mode,
    account?.districtId ?? null
  );
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
        if (
          !abort.signal.aborted &&
          current === epoch.current &&
          latestIdentity.current === identity
        ) {
          setSaved(next);
          if (ground) onInstalled?.(ground);
        }
      }
      if (
        !abort.signal.aborted &&
        current === epoch.current &&
        latestIdentity.current === identity
      ) {
        if (remove?.id === saved?.id) setSaved(null);
        setRevision((v) => v + 1);
      }
    } catch (e) {
      if (!abort.signal.aborted && current === epoch.current && latestIdentity.current === identity)
        setError(errorMessage(e));
    } finally {
      if (current === epoch.current && latestIdentity.current === identity) {
        setBusy(false);
        posting.current = null;
      }
    }
  }
  return {
    mode,
    allowed,
    specifications,
    specification,
    specificationId: currentScope ? specificationId : '',
    specificationError,
    specificationsLoading,
    chooseSpecification: (id: string) => {
      setSaved(null);
      setSpecificationId(id);
    },
    role,
    setRole,
    roof: currentScope ? roof : null,
    ground: currentScope ? ground : null,
    capture: currentScope ? capture : '',
    area: currentScope ? area : '',
    depth: currentScope ? depth : '',
    edit,
    layoutFields: currentScope ? layoutFields : emptyLayout,
    geometry,
    editLayout: (key: keyof CisternLayoutFields, value: string) => {
      setSaved(null);
      setLayoutFields((v) => ({ ...v, [key]: value }));
    },
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
