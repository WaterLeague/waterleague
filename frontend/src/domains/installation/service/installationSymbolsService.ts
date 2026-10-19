import { siteKey, type SharedInstallation, type SharedSite } from '../entity/installation';
import { representativeInstallations } from './memberSitesService';
import { detailLabelDistance } from '../../city/service/cityService';

export function installationSymbols(
  installations: SharedInstallation[],
  sites: SharedSite[],
  viewerId: string | null,
  distance: number
) {
  const detailed = new Set(distance < detailLabelDistance ? sites.map(siteKey) : []);
  return [...representativeInstallations(installations, viewerId).values()].filter(
    (value) => !detailed.has(siteKey(value))
  );
}
