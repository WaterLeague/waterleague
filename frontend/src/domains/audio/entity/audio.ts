import type { RefObject } from 'react';
import type { GameAudioEngine } from '../service/gameAudioEngine';

export type SoundPoint = readonly [number, number, number];
export type StreetSound = {
  id: string;
  kind: 'car' | 'walk';
  point: SoundPoint;
  speed: number;
};
export type AudioHandle = RefObject<GameAudioEngine | null>;
export type AmbientSound = {
  playing: boolean;
  speed: number;
  rain: number;
  distance: number;
  flood: { point: SoundPoint; depth: number | null; speed: number | null } | null;
};
