import { type SharedInstallation } from '../entity/installation';
import { representativeInstallations } from './memberSitesService';

export function installationSymbols(installations: SharedInstallation[], viewerId: string | null) {
  return [...representativeInstallations(installations, viewerId).values()];
}
