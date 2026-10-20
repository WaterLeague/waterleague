import { afterEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import publicRaw from '../../../../../backend/src/main/resources/facilities/cistern-specifications-v1.json?raw';
import nativeSites from '../__tests__/fixtures/nativeSites.json';
import catalogRaw from '../../watershed/view/fixtures/catalog.json';
import { siteDto } from '../dto/installationDto';
import { cisternPlanDto } from '../dto/cisternPlanDto';
import { cisternSpecificationCatalogDto } from '../../facility/dto/cisternSpecificationDto';
import { loadCisternSpecifications } from '../../facility/repository/cisternSpecificationRepository';
import { loadCisternPlans } from '../repository/cisternPlanRepository';
import { cisternEquipmentPlanRequest } from './cisternPlanService';
import { cisternEquipmentGeometry, parseCisternEquipment } from './cisternLayoutService';
import { watershedCatalogDto } from '../../watershed/dto/watershedDto';
import { previewCisternCosts } from '../../watershed/service/cisternCosts';
import { CisternLayoutPlan } from '../view/CisternLayoutPlan';
import { CisternPlanPanel } from '../view/CisternPlanPanel';
import type { CisternPlanState } from '../controller/useCisternPlans';
import type { MapPoint } from '../../catalog/entity/facilityFootprint';
const spec = cisternSpecificationCatalogDto.parse(JSON.parse(publicRaw)).specifications[0];
const fields = { width: '', wall: '', east: '0', north: '0', rotation: '0' };
const equipment = parseCisternEquipment(fields, spec.id)!;
const roof = siteDto.parse(nativeSites.roof);
// 공간 경계 회귀용 합성 도형이며 운영 입지 자료가 아니다.
const ground = {
  ...siteDto.parse(nativeSites.ground),
  center: [0, 0] as MapPoint,
  polygons: [
    [
      [
        [-5, -5],
        [5, -5],
        [5, 5],
        [-5, 5],
        [-5, -5],
      ],
    ],
  ] as MapPoint[][][],
};
function draft() {
  return {
    id: '10000000-0000-4000-8000-000000000001',
    inputHash: 'a'.repeat(64),
    createdAt: '2026-10-20T00:00:00Z',
    snapshot: {
      schemaVersion: 3,
      status: 'SPATIAL_DRAFT_NOT_INSTALLED',
      request: cisternEquipmentPlanRequest(roof, ground, '20', equipment, spec)!,
      roof,
      ground,
      capacityM3: 1.5,
      capacityBasis: spec.capacityBasis,
      equipmentSpecification: spec,
      equipmentGeometry: cisternEquipmentGeometry(ground, spec, equipment)!,
      horizontalSeparationM: 10,
      referenceCosts: previewCisternCosts(watershedCatalogDto.parse(catalogRaw), [], {
        id: 'CisternPlan',
        catchmentId: 'S9',
        captureAreaM2: 20,
        areaM2: 1.5,
        depthM: 1,
        invertM: 0,
        initialDepthM: 0,
        drain: { crestM: 0, diameterM: 0.1, dischargeCoefficient: 0.6, flapGate: true },
        overflow: { crestM: 1, diameterM: 0.1, dischargeCoefficient: 0.6, flapGate: true },
      }),
      installationReady: false,
      positionReserved: false,
      limitations: [],
    },
  };
}
afterEach(() => vi.unstubAllGlobals());
it('공개 외형과 명목 용량 분리 및 구멍·경계 침범 차단', () => {
  const geometry = cisternEquipmentGeometry(ground, spec, equipment)!;
  expect(geometry.contained).toBe(true);
  expect(geometry.widthM * geometry.lengthM * geometry.heightM).not.toBe(spec.nominalCapacityM3);
  expect(geometry).not.toHaveProperty('storageDepthM');
  expect(cisternEquipmentGeometry(ground, spec, { ...equipment, offsetXM: 5 })?.contained).toBe(
    false
  );
  const hole: MapPoint[] = [
    [-0.1, -0.1],
    [0.1, -0.1],
    [0.1, 0.1],
    [-0.1, 0.1],
    [-0.1, -0.1],
  ];
  expect(
    cisternEquipmentGeometry(
      { ...ground, polygons: [[ground.polygons[0][0], hole]] },
      spec,
      equipment
    )?.contained
  ).toBe(false);
  expect(parseCisternEquipment({ ...fields, east: '0.0001' }, spec.id)).toBeNull();
  const markup = renderToStaticMarkup(
    <svg>
      <CisternLayoutPlan geometry={geometry} />
    </svg>
  );
  expect(markup.match(/<path/g)).toHaveLength(1);
  expect(markup).toContain('공개 장비 외형');
});
it('보존 규격·배치·용량 변조와 내부 설계 혼입 거부', () => {
  expect(cisternPlanDto.safeParse(draft()).success).toBe(true);
  const changes: ((p: ReturnType<typeof draft>) => void)[] = [
    (p) => {
      p.snapshot.capacityM3 = 2.088;
    },
    (p) => {
      p.snapshot.equipmentGeometry.widthM = 1;
    },
    (p) => {
      p.snapshot.equipmentGeometry.coordinates[0][0] += 0.1;
    },
    (p) => {
      p.snapshot.request.equipment!.catalogSha256 = '0'.repeat(64);
    },
    (p) => {
      p.snapshot.request.tankAreaM2 = 1.44;
    },
    (p) => {
      p.snapshot.schemaVersion = 2;
    },
    (p) => {
      p.snapshot.installationReady = true;
    },
  ];
  for (const change of changes) {
    const p = structuredClone(draft());
    change(p);
    expect(cisternPlanDto.safeParse(p).success).toBe(false);
  }
  expect(
    cisternEquipmentPlanRequest(
      { ...roof, siteEligibility: 'PROHIBITED' },
      ground,
      '20',
      equipment,
      spec
    )
  ).toBeNull();
  expect(cisternEquipmentPlanRequest(roof, ground, '20.001', equipment, spec)).toBeNull();
});
it('해시 검증된 공개 카탈로그와 저장 규격을 다시 대조', async () => {
  let plan = structuredClone(draft());
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (url: string) =>
        new Response(url.endsWith('cistern-plans') ? JSON.stringify([plan]) : publicRaw)
    )
  );
  expect((await loadCisternPlans())[0].snapshot.equipmentSpecification).toEqual(spec);
  plan.snapshot.equipmentSpecification.material = 'ALTERED';
  await expect(loadCisternPlans()).rejects.toThrow('공개 원자료');
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(publicRaw.replace('1.45', '1.46')))
  );
  await expect(loadCisternSpecifications(new AbortController().signal)).rejects.toThrow(
    '공개 이용조 규격'
  );
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('x'.repeat(65537)))
  );
  await expect(loadCisternSpecifications(new AbortController().signal)).rejects.toThrow(
    '공개 이용조 규격'
  );
});
it('공개 장비 선택의 표시·공종·공사비 미확정과 저장 구분', () => {
  const noop = () => {},
    plan = cisternPlanDto.parse(draft());
  const state: CisternPlanState = {
    allowed: true,
    specifications: [spec],
    specification: spec,
    specificationId: spec.id,
    specificationError: '',
    specificationsLoading: false,
    chooseSpecification: noop,
    role: 'ground',
    setRole: noop,
    roof,
    ground,
    capture: '20',
    area: '',
    depth: '',
    edit: noop,
    layoutFields: fields,
    geometry: plan.snapshot.equipmentGeometry!,
    editLayout: noop,
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
  const html = renderToStaticMarkup(
    <CisternPlanPanel state={state} onClose={noop} onChoose={noop} onLocate={noop} onLogin={noop} />
  );
  expect(html).toContain('명목 용량 1.5');
  expect(html).toContain('장비 외형 폭 0.8 × 길이 1.8 × 높이 1.45m');
  expect(html).toContain('22,000,000원');
  expect(html).toContain('확정 설치비와 게임 예산으로 사용하지 않습니다');
  expect(html).toContain('기초·계장 공사');
  expect(html).not.toContain('내부 수면적 (m²)');
  expect(html).not.toContain('이 위치에 설치');
});
