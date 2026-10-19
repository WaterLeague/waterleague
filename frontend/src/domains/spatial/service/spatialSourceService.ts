import distribution from '../../../../../data/manifests/vworld-seongdong-topography-20260307.json';

export const topographySource = {
  label: `${distribution.distributionUpdatedAt} 갱신 수치지형도`,
  updatedAt: distribution.distributionUpdatedAt,
  url: distribution.sourceUrl,
} as const;
