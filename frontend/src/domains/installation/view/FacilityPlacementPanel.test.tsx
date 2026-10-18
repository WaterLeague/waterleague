import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import rawSite from './fixtures/basinSite.json';
import { siteDto } from '../dto/installationDto';
import { FacilityPlacementPanel, type FacilityPlacementProps } from './FacilityPlacementPanel';

const site = siteDto.parse(rawSite);
const props: FacilityPlacementProps = {
  site,
  type: 'PERMEABLE_PAVEMENT',
  area: '1',
  onType: () => {},
  onArea: () => {},
  onInstall: () => {},
  districtName: '송파구',
  context: '내 소속 구',
  budget: null,
  remaining: 2_000_000_000,
  limit: 2_000_000_000,
  budgetReady: true,
  busy: false,
  canInstall: true,
};

it('주간·재해 공통 패널에서 공개 경계 교차 사유 표시와 신규 배치 폼 제외', () => {
  for (const research of [false, true]) {
    const html = renderToStaticMarkup(<FacilityPlacementPanel {...props} research={research} />);
    expect(html).toContain('공개 지도 저류 영역 · 신규 설치 제외');
    expect(html).toContain('잠실유수지');
    expect(html).toContain('교차 100 m²');
    expect(html).not.toContain('<form');
    expect(html).not.toContain('이 위치에 설치');
    expect(html).not.toContain('연구 설계에 추가');
  }
});

it('공개 경계와 겹치는 이전 설치 기록은 보존하고 주간 철거 금지', () => {
  const html = renderToStaticMarkup(
    <FacilityPlacementPanel
      {...props}
      occupied={{
        facilityType: 'PERMEABLE_PAVEMENT',
        areaM2: 1,
        cost: 110000,
        ownerName: '내 시설',
        onRemove: () => {},
      }}
    />
  );
  expect(html).toContain('설치 완료');
  expect(html).not.toContain('내 시설 철거');
  expect(html).toContain('시즌 종료까지 변경·철거할 수 없습니다.');
  expect(html).not.toContain('<form');
});

it('공통 패널의 생물저류 제원 선택과 같은 사업군 잔액 적용', () => {
  const bio = siteDto.parse({
    ...rawSite,
    existingInfrastructure: null,
    allowedTypes: ['BIORETENTION'],
    unitCosts: { ...rawSite.unitCosts, BIORETENTION: 560000 },
    costModel: {
      ...rawSite.costModel,
      facilities: {
        ...rawSite.costModel.facilities,
        BIORETENTION: { ...rawSite.costModel.facilities.RAIN_GARDEN, unitCost: 560000 },
      },
    },
  });
  for (const research of [false, true]) {
    const html = renderToStaticMarkup(
      <FacilityPlacementPanel
        {...props}
        site={bio}
        type="BIORETENTION"
        area="20"
        research={research}
        budgetAccounting={{
          version: 'SEOUL_RAINWATER_ACCOUNTING_V2',
          programs: [],
          facilities: [
            {
              facilityType: 'BIORETENTION',
              programId: 'SEOUL_RAINWATER',
              limitKrw: null,
              allocatedKrw: 0,
              availableKrw: 2_000_000_000,
            },
          ],
        }}
      />
    );
    expect(html).toContain('생물저류시설');
    expect(html).toContain('11,200,000원');
    expect(html).toContain(research ? '연구 설계에 추가' : '생물저류시설 설치 확정');
    expect(html).not.toContain('class="solid-button shared-install" disabled');
  }
});

it('식생수로는 주간·재해 모두 폭 기준 한도 초과 설치 거부', () => {
  const swale = siteDto.parse({
    ...rawSite,
    existingInfrastructure: null,
    allowedTypes: ['VEGETATIVE_SWALE'],
    unitCosts: { ...rawSite.unitCosts, VEGETATIVE_SWALE: 45000 },
    costModel: {
      ...rawSite.costModel,
      facilities: {
        ...rawSite.costModel.facilities,
        VEGETATIVE_SWALE: { ...rawSite.costModel.facilities.RAIN_GARDEN, unitCost: 45000 },
      },
    },
    physicalInputs: {
      flowLengthM: 5,
      runoffWidthM: 5,
      widthMethod: 'FOOTPRINT_AREA_OVER_LONG_AXIS',
      slopePercent: 1,
      slopeMethod: 'NGII_2025_90M_HORN_TERRAIN_PROXY',
      surfaceTag: null,
      imperviousBasis: 'SURFACE_UNKNOWN_ASSUMPTION',
      soilStatus: 'TEXTURE_CLASS_LITERATURE_ESTIMATE',
      swaleDesign: {
        method: 'CONTAINED_FIXED_WIDTH_STRAIGHT_DESIGN_V1',
        topWidthM: 2,
        maxAreaM2: 10,
        maxLengthM: 5,
        center: [0, 0],
        direction: [1, 0],
        coordinates: [
          [-2.5, -1],
          [2.5, -1],
          [2.5, 1],
          [-2.5, 1],
          [-2.5, -1],
        ],
        slopeBasis: 'REGIONAL_TERRAIN_PROXY_NOT_LONGITUDINAL_SURVEY',
        outlet: 'SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK',
      },
    },
  });
  for (const research of [false, true])
    for (const area of ['10', '10.01']) {
      const html = renderToStaticMarkup(
        <FacilityPlacementPanel
          {...props}
          site={swale}
          type="VEGETATIVE_SWALE"
          area={area}
          research={research}
          budgetAccounting={{
            version: 'SEOUL_RAINWATER_ACCOUNTING_V3',
            programs: [],
            facilities: [
              {
                facilityType: 'VEGETATIVE_SWALE',
                programId: 'SEOUL_RAINWATER',
                limitKrw: null,
                allocatedKrw: 0,
                availableKrw: 2_000_000_000,
              },
            ],
          }}
        />
      );
      expect(html).toContain('폭 2m 직선 배치 한도');
      expect(html.includes('class="solid-button shared-install" disabled')).toBe(area === '10.01');
      if (area === '10') expect(html).toContain('450,000원');
    }
});

it('침투 트렌치는 주간·재해 모두 폭 기준 한도 초과 설치 거부', () => {
  const trench = siteDto.parse({
    ...rawSite,
    existingInfrastructure: null,
    allowedTypes: ['INFILTRATION_TRENCH'],
    unitCosts: { ...rawSite.unitCosts, INFILTRATION_TRENCH: 171429 },
    costModel: {
      ...rawSite.costModel,
      facilities: {
        ...rawSite.costModel.facilities,
        INFILTRATION_TRENCH: { ...rawSite.costModel.facilities.RAIN_GARDEN, unitCost: 171429 },
      },
    },
    physicalInputs: {
      flowLengthM: 5,
      runoffWidthM: 5,
      widthMethod: 'FOOTPRINT_AREA_OVER_LONG_AXIS',
      slopePercent: 1,
      slopeMethod: 'NGII_2025_90M_HORN_TERRAIN_PROXY',
      surfaceTag: null,
      imperviousBasis: 'SURFACE_UNKNOWN_ASSUMPTION',
      soilStatus: 'TEXTURE_CLASS_LITERATURE_ESTIMATE',
      trenchDesign: {
        method: 'CONTAINED_FIXED_WIDTH_STRAIGHT_DESIGN_V1',
        topWidthM: 1,
        maxAreaM2: 10,
        maxLengthM: 10,
        center: [0, 0],
        direction: [1, 0],
        coordinates: [
          [-2.5, -1],
          [2.5, -1],
          [2.5, 1],
          [-2.5, 1],
          [-2.5, -1],
        ],
        slopeBasis: 'LEVEL_STORAGE_DESIGN_NOT_SURVEY',
        outlet: 'SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK',
      },
    },
  });
  for (const research of [false, true])
    for (const area of ['10', '10.01']) {
      const html = renderToStaticMarkup(
        <FacilityPlacementPanel
          {...props}
          site={trench}
          type="INFILTRATION_TRENCH"
          area={area}
          research={research}
          budgetAccounting={{
            version: 'SEOUL_RAINWATER_ACCOUNTING_V4',
            programs: [],
            facilities: [
              {
                facilityType: 'INFILTRATION_TRENCH',
                programId: 'SEOUL_RAINWATER',
                limitKrw: null,
                allocatedKrw: 0,
                availableKrw: 2_000_000_000,
              },
            ],
          }}
        />
      );
      expect(html).toContain('폭 1m 직선 배치 한도');
      expect(html.includes('class="solid-button shared-install" disabled')).toBe(area === '10.01');
      if (area === '10') expect(html).toContain('1,714,290원');
    }
});
