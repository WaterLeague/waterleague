import { siteKey, type SharedInstallation } from '../entity/installation';

export function representativeInstallations(values: SharedInstallation[], viewerId: string | null) {
  const sites = new Map<string, SharedInstallation>();
  for (const value of values) {
    const key = siteKey(value),
      previous = sites.get(key);
    if (
      !previous ||
      (value.ownerId === viewerId && previous.ownerId !== viewerId) ||
      (value.ownerId === previous.ownerId && value.id < previous.id) ||
      (value.ownerId !== viewerId && previous.ownerId !== viewerId && value.id < previous.id)
    )
      sites.set(key, value);
  }
  return sites;
}
