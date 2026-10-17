import { z } from 'zod';
export const cityEligibilityDto = z.object({
  schemaVersion: z.literal(1),
  catalogSha256: z.literal('f26b639dbdb2fee3c1aff172a19153868a07aa70735a6dfcfda863c3a38e8b64'),
  roofSourceIds: z.array(z.string().regex(/^(way|relation)\/\d+$/)).max(200000),
  legacySiteSources: z.record(z.string(), z.array(z.string())),
});
export type CityEligibility = {
  roofIds: ReadonlySet<string>;
  legacySiteSources: Record<string, string[]>;
};
