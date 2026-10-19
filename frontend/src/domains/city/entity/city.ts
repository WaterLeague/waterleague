import type { z } from 'zod';
import type { cityDto, cityTileDto, cityBuildingDto } from '../dto/cityDto';
export type City = z.infer<typeof cityDto>;
export type CityTile = z.infer<typeof cityTileDto>;
export type CityBuilding = z.infer<typeof cityBuildingDto> & { baseElevationM?: number };
export type TileEntry = City['tiles'][number];
export type CityFocus = {
  center: [number, number];
  distance: number;
  heightM?: number;
  key: number;
  overview?: boolean;
  preserveAngle?: boolean;
};
