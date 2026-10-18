import type { SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';

export function placementAreaLimit(site: SharedSite, type: FacilityType | '') {
  return type === 'VEGETATIVE_SWALE'
    ? Math.min(site.maxAreaM2, site.physicalInputs?.swaleDesign?.maxAreaM2 ?? 0)
    : type === 'INFILTRATION_TRENCH'
      ? Math.min(site.maxAreaM2, site.physicalInputs?.trenchDesign?.maxAreaM2 ?? 0)
      : site.maxAreaM2;
}
