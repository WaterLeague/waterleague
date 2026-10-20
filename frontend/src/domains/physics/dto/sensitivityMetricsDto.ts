import { z } from 'zod';

const value = z.number().finite();
export const sensitivityMetricsDto = z.object({
  initialSoilMoisture: value.nullable(),
  initialStorageM3: value,
  initialLidStorageM3: value.nullable(),
  initialSurfaceDepthMm: value.nullable(),
  initialPavementDepthMm: value.nullable(),
  initialStorageDepthMm: value.nullable(),
  evaluatedDischargeM3: value,
  evaluatedEvaporationM3: value,
  evaluatedInfiltrationM3: value,
  peakDischargeMean1MinM3s: value,
  contributionM3: value,
});
