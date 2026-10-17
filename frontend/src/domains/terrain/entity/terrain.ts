export type Terrain = {
  width: number;
  height: number;
  origin: [number, number];
  spacing: [number, number];
  districtIds: string[];
  heights: Float32Array;
  districts: Uint8Array;
  cover: Uint8Array;
};
