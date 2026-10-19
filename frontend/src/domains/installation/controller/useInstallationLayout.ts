import { useMemo } from 'react';
import type { SharedInstallation, InstallationLayout } from '../entity/installation';
import { installationLayoutKey } from '../service/installationLayoutService';
import { representativeInstallations } from '../service/memberSitesService';

export function useInstallationLayout(values: SharedInstallation[], viewerId: string | null) {
  const key = installationLayoutKey(values);
  const placements = useMemo(() => JSON.parse(key) as InstallationLayout[], [key]);
  const bySite = useMemo(
    () => representativeInstallations(placements, viewerId),
    [placements, viewerId]
  );
  return { placements, bySite };
}
