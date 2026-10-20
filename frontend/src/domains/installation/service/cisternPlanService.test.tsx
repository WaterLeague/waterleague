import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import nativeSites from '../__tests__/fixtures/nativeSites.json';
const rawSite = nativeSites.ground;
import catalogRaw from '../../watershed/view/fixtures/catalog.json';
import { siteDto } from '../dto/installationDto';
import { cisternPlanDto } from '../dto/cisternPlanDto';
import { cisternRequest, cisternSelectionError } from './cisternPlanService';
import { watershedCatalogDto } from '../../watershed/dto/watershedDto';
import { previewCisternCosts } from '../../watershed/service/cisternCosts';
import { CisternPlanPanel } from '../view/CisternPlanPanel';
import type { CisternPlanState } from '../controller/useCisternPlans';
import { cisternGeometry } from './cisternLayoutService';

// 공개 후보 구조를 사용하는 단위 검사이며 운영 입지·설계 자료로 사용하지 않는다.
const ground = siteDto.parse(rawSite);
const roof = siteDto.parse(nativeSites.roof);
const catalog = watershedCatalogDto.parse(catalogRaw);
function draft() {
  return {
    id: '10000000-0000-4000-8000-000000000001',
    inputHash: 'a'.repeat(64),
    createdAt: '2026-10-19T00:00:00Z',
    snapshot: {
      schemaVersion: 1,
      status: 'SPATIAL_DRAFT_NOT_INSTALLED',
      request: cisternRequest(roof, ground, '20', '1', '2.35')!,
      roof,
      ground,
      capacityM3: 2.35,
      horizontalSeparationM: 10,
      referenceCosts: previewCisternCosts(catalog, [], {
        id: 'CisternPlan',
        catchmentId: 'S9',
        captureAreaM2: 20,
        areaM2: 1,
        depthM: 2.35,
        invertM: 0,
        initialDepthM: 0,
        drain: { crestM: 0, diameterM: 0.1, dischargeCoefficient: 0.6, flapGate: true },
        overflow: { crestM: 2.3, diameterM: 0.1, dischargeCoefficient: 0.6, flapGate: true },
      }),
      installationReady: false,
      positionReserved: false,
      limitations: [],
    },
  };
}
it('지붕·지상의 종류, 소속 구, 점유와 공개 저류 경계에 따른 선택 제한', () => {
  expect(cisternSelectionError(roof, 'roof', roof.districtId, false)).toBe('');
  expect(cisternSelectionError(ground, 'roof', null, false)).toContain('지붕');
  expect(cisternSelectionError(roof, 'ground', null, false)).toContain('지상');
  expect(cisternSelectionError(ground, 'ground', '0000000', false)).toContain('소속 구');
  expect(cisternSelectionError(ground, 'ground', ground.districtId, true)).toContain('이미');
  expect(cisternSelectionError(siteDto.parse(nativeSites.reference), 'ground', null, false)).toBe(
    ''
  );
});
it('공개 면적 한계와 입력 정밀도·종류·구 불일치 차단', () => {
  expect(cisternRequest(roof, ground, '20', '1', '2.350')?.tankDepthM).toBe(2.35);
  for (const values of [
    ['0', '1', '2'],
    ['20', '1.001', '2'],
    ['20', '1', '0.0001'],
    ['20', '1', '101'],
    ['20', '1', 'Infinity'],
    [String(roof.maxAreaM2 + 1), '1', '2'],
    ['20', String(ground.maxAreaM2 + 1), '2'],
  ])
    expect(cisternRequest(roof, ground, ...(values as [string, string, string]))).toBeNull();
  expect(cisternRequest(roof, { ...ground, districtId: '0000000' }, '20', '1', '2')).toBeNull();
  expect(cisternRequest(ground, roof, '20', '1', '2')).toBeNull();
});
it('이용조 공간 초안도 금지·미충족 조건부의 선택·저장 차단', () => {
  for (const siteEligibility of ['PROHIBITED', 'CONDITIONAL'] as const) {
    const blockedRoof = { ...roof, siteEligibility },
      blockedGround = { ...ground, siteEligibility };
    expect(cisternSelectionError(blockedRoof, 'roof', null, false)).toContain('안전 조건');
    expect(cisternSelectionError(blockedGround, 'ground', null, false)).toContain('안전 조건');
    expect(cisternRequest(blockedRoof, ground, '20', '1', '2')).toBeNull();
    expect(cisternRequest(roof, blockedGround, '20', '1', '2')).toBeNull();
  }
});
it('복원 응답의 원본 버전·두 위치·용량·견적 결속 검사', () => {
  expect(cisternPlanDto.safeParse(draft()).success).toBe(true);
  const changes = [
    (x: ReturnType<typeof draft>) => {
      x.snapshot.roof.modelHash = 'b'.repeat(64);
    },
    (x: ReturnType<typeof draft>) => {
      x.snapshot.request.groundCellId = 'GOTHER';
    },
    (x: ReturnType<typeof draft>) => {
      x.snapshot.request.tankDepthM = 4.7;
    },
    (x: ReturnType<typeof draft>) => {
      x.snapshot.referenceCosts!.items = [];
    },
    (x: ReturnType<typeof draft>) => {
      x.snapshot.installationReady = true;
    },
  ];
  for (const change of changes) {
    const value = structuredClone(draft());
    change(value);
    expect(cisternPlanDto.safeParse(value).success).toBe(false);
  }
});
it('형상 포함 계획의 수량·배치 결속과 이전 면적 계획 구분', () => {
  const base = structuredClone(draft());
  const site = {
    ...base.snapshot.ground,
    center: [0, 0] as [number, number],
    polygons: [
      [
        [
          [-5, -5],
          [5, -5],
          [5, 5],
          [-5, 5],
          [-5, -5],
        ] as [number, number][],
      ],
    ],
  };
  const layout = { widthM: 1, wallThicknessM: 0.1, offsetXM: 0, offsetYM: 0, rotationDeg: 0 };
  const value = {
    ...base,
    snapshot: {
      ...base.snapshot,
      schemaVersion: 2,
      ground: site,
      request: { ...base.snapshot.request, tankLayout: layout },
      tankGeometry: cisternGeometry(site, 1, 2.35, layout)!,
    },
  };
  expect(cisternPlanDto.safeParse(value).success).toBe(true);
  const changed = structuredClone(value);
  changed.snapshot.tankGeometry.coordinates[0][0] += 0.1;
  expect(cisternPlanDto.safeParse(changed).success).toBe(false);
  const changedWidth = structuredClone(value);
  changedWidth.snapshot.request.tankLayout.widthM = 2;
  expect(cisternPlanDto.safeParse(changedWidth).success).toBe(false);
  const old = structuredClone(value);
  old.snapshot.schemaVersion = 1;
  expect(cisternPlanDto.safeParse(old).success).toBe(false);
  expect(cisternPlanDto.parse(base).snapshot.tankGeometry).toBeUndefined();
});
it('저장된 참고 견적과 계획 안내를 표시하고 비회원 저장 버튼 분리', () => {
  const plan = cisternPlanDto.parse(draft());
  const noop = () => {};
  const state: CisternPlanState = {
    allowed: true,
    role: 'ground',
    setRole: noop,
    roof,
    ground,
    capture: '20',
    layoutFields: { width: '', wall: '', east: '0', north: '0', rotation: '0' },
    geometry: null,
    editLayout: noop,
    area: '1',
    depth: '2.35',
    edit: noop,
    plans: [plan],
    saved: plan,
    error: '',
    busy: false,
    loading: false,
    select: () => true,
    restore: noop,
    valid: true,
    save: async () => {},
    remove: async () => {},
    retry: noop,
  };
  const props = { state, onChoose: noop, onClose: noop, onLocate: noop, onLogin: noop };
  const html = renderToStaticMarkup(<CisternPlanPanel {...props} />);
  expect(html).toContain('지도 계획 저장');
  expect(html).toContain('설계 용량 2.35');
  expect(html).toContain('5,447,000원');
  expect(html).toContain('위치 예약 및 설치 없음');
  expect(html).not.toContain('이 위치에 설치');
  const visitor = renderToStaticMarkup(
    <CisternPlanPanel {...props} state={{ ...state, allowed: false, plans: [], saved: null }} />
  );
  expect(visitor).toContain('로그인하고 계획 저장');
});
