import { z } from 'zod';
export const CISTERN_SPECIFICATIONS_HASH =
  '6fdf0d866bb28901196cd4354a786228fa1a53b77a3d8c8e805e5d9744edde17';
const positive = z.number().finite().positive();
const money = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
export const cisternSpecificationDto = z.object({
  id: z.string().regex(/^[A-Z0-9_]{1,80}$/),
  name: z.string().min(1).max(200),
  material: z.string().min(1).max(100),
  nominalCapacityM3: positive,
  capacityBasis: z.literal('NOMINAL_WATER_TONNE_EQUIVALENT_NOT_MEASURED_USABLE_VOLUME'),
  declaredCapacity: z.string(),
  equipmentDimensionsM: z.object({ length: positive, width: positive, height: positive }),
  dimensionBasis: z.literal('EQUIPMENT_ENVELOPE_NOT_INTERNAL_STORAGE'),
  hydraulics: z.object({
    internalAreaM2: z.null(),
    usableDepthM: z.null(),
    drainElevationM: z.null(),
    overflowElevationM: z.null(),
    overflowDiameterM: z.null(),
    pumpCurve: z.null(),
    reuseDemand: z.null(),
  }),
  pumpDutyPoint: z.object({
    model: z.string(),
    flowLMin: positive,
    headM: positive,
    powerHp: positive,
    basis: z.literal('SINGLE_DUTY_POINT_NOT_PUMP_CURVE'),
  }),
  procurement: z
    .object({
      classification: z.literal('PROJECT_BUDGET_NOT_TRANSACTION_PRICE'),
      basisMonth: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
      currency: z.literal('KRW'),
      netKrw: money,
      vatKrw: money,
      grossKrw: money,
      confirmedInstallationPriceKrw: z.null(),
      scope: z.array(z.string()).min(1),
      limitations: z.array(z.string()).min(1),
    })
    .refine((p) => p.netKrw + p.vatKrw === p.grossKrw),
  sources: z
    .array(
      z.object({
        title: z.string(),
        url: z.url().refine((v) => v.startsWith('https://')),
        sha256: z.string().regex(/^[a-f0-9]{64}$/),
        pages: z.array(z.number().int().positive()).min(1),
      })
    )
    .min(1),
  installationReady: z.literal(false),
  limitations: z.array(z.string()).min(1),
});
export const cisternSpecificationCatalogDto = z.object({
  schemaVersion: z.literal(1),
  version: z.literal('PUBLIC_CISTERN_SPECIFICATIONS_V1'),
  specifications: z.array(cisternSpecificationDto).min(1).max(100),
});
export type CisternSpecification = z.infer<typeof cisternSpecificationDto>;
