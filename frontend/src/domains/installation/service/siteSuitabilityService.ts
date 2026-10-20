import type { SharedSite } from '../entity/installation';

export function sitePlacementRestricted(site: SharedSite) {
  return (
    site.suitability?.explorationAllowed === false ||
    ['PROHIBITED', 'CONDITIONAL'].includes(site.siteEligibility ?? 'UNKNOWN')
  );
}
