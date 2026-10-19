import type { RefObject } from 'react';
export type Street = {
  id: string;
  class: string;
  districtId: string;
  widthM: number;
  widthSource: 'OSM_WIDTH_TAG' | 'DISPLAY_ASSUMPTION';
  walk: boolean;
  motor: boolean;
  oneway: number;
  sidewalk: string;
  bridge: boolean;
  coordinates: [number, number][];
};
export type UrbanTime = RefObject<{
  historical: boolean;
  at: number | null;
  playing: boolean;
  speed: number;
  sampledAt: number;
  listeners?: Set<() => void>;
}>;
export type Population = {
  event2022: Record<string, number[]>;
  reference2025: Record<string, number[]>;
};
