import type { MapDto } from '../dto/catalogDto';
export type Building = Extract<MapDto['features'][number], { kind: 'building' }>;
export type Road = Extract<MapDto['features'][number], { kind: 'road' }>;
export interface CandidateMap { snapshot: MapDto; buildings: Building[]; roads: Road[]; }
