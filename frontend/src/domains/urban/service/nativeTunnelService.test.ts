import { expect, test } from 'vitest';
import {
  tunnelHeight,
  nativeTunnelStreets,
  attachNativeTunnels,
  type NativeTunnel,
  connectTunnelProfiles,
} from './nativeTunnelService';
import { streetGeometry, streetHeight } from './streetGeometryService';
import type { Terrain } from '../../terrain/entity/terrain';
const terrain: Terrain = {
  width: 3,
  height: 2,
  origin: [0, -10],
  spacing: [50, 20],
  districtIds: [],
  heights: new Float32Array([10, 50, 12, 10, 50, 12]),
  districts: new Uint8Array(6),
  cover: new Uint8Array(6),
};
const tunnel: NativeTunnel = {
  id: 'ngii:N1A_A0110020:' + 'a'.repeat(64),
  sourceFid: 1,
  name: '검증 터널',
  polygons: [
    [
      [
        [0, -5],
        [100, -5],
        [100, 5],
        [0, 5],
        [0, -5],
      ],
    ],
  ],
  profiles: [
    {
      roadId: 'ngii:N1L_A0020000:' + 'b'.repeat(64),
      coordinates: [
        [0, 0],
        [100, 0],
      ],
    },
  ],
  clearanceM: 4.5,
};
test('터널 내부 포장·차량은 산 표면이 아닌 입구 표고 사이를 따르고 원 높이 속성으로 천장 생성', () => {
  expect(tunnelHeight(tunnel, [0, 0], terrain)).toBe(10);
  expect(tunnelHeight(tunnel, [50, 0], terrain)).toBe(11);
  expect(tunnelHeight(tunnel, [100, 0], terrain)).toBe(12);
  const road = nativeTunnelStreets([tunnel])[0];
  const mesh = streetGeometry([road], terrain, true);
  expect(Math.max(...Array.from(mesh.positions).filter((_, i) => i % 3 === 1))).toBeLessThan(17);
  const moving = attachNativeTunnels(
    [
      {
        ...road,
        id: tunnel.profiles[0].roadId + ':part:0',
        nativeSourceRole: 'ROAD_CENTERLINE',
        nativeTunnels: undefined,
      },
    ],
    [tunnel]
  )[0];
  expect(streetHeight(terrain, [50, 0], moving)).toBeCloseTo(11.016);
});

test('도엽 경계에서 나뉜 같은 터널의 원 끝점 연결과 종단 높이 유지', () => {
  const a = {
    ...tunnel,
    polygons: [
      [
        [
          [0, -5],
          [50, -5],
          [50, 5],
          [0, 5],
          [0, -5],
        ],
      ],
    ] as [number, number][][][],
    profiles: [
      {
        ...tunnel.profiles[0],
        coordinates: [
          [0, 0],
          [50, 0],
        ] as [number, number][],
      },
    ],
  };
  const b = {
    ...tunnel,
    id: 'other',
    polygons: [
      [
        [
          [50, -5],
          [100, -5],
          [100, 5],
          [50, 5],
          [50, -5],
        ],
      ],
    ] as [number, number][][][],
    profiles: [
      {
        ...tunnel.profiles[0],
        coordinates: [
          [50, 0],
          [100, 0],
        ] as [number, number][],
      },
    ],
  };
  const connected = connectTunnelProfiles([a, b]);
  expect(tunnelHeight(connected[0], [50, 0], terrain)).toBe(11);
  expect(tunnelHeight(connected[1], [50, 0], terrain)).toBe(11);
});
