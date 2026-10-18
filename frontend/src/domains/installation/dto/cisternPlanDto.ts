import { z } from 'zod';
import { siteDto } from './installationDto';
import { cisternCostSnapshotDto } from '../../watershed/dto/cisternCostDto';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const cisternPlanRequestDto = z.object({
  districtId: z.string().regex(/^\d{7}$/),
  roofCellId: z.string().regex(/^R[A-Z0-9-]{1,19}$/),
  groundCellId: z.string().regex(/^G[A-Z0-9-]{1,19}$/),
  roofModelHash: hash,
  groundModelHash: hash,
  captureAreaM2: z.number().finite().positive(),
  tankAreaM2: z.number().finite().positive(),
  tankDepthM: z.number().finite().min(0.001).max(100),
});
export const cisternPlanDto = z
  .object({
    id: z.uuid(),
    inputHash: hash,
    createdAt: z.iso.datetime(),
    snapshot: z.object({
      schemaVersion: z.literal(1),
      status: z.literal('SPATIAL_DRAFT_NOT_INSTALLED'),
      request: cisternPlanRequestDto,
      roof: siteDto,
      ground: siteDto,
      capacityM3: z.number().finite().positive(),
      horizontalSeparationM: z.number().finite().nonnegative(),
      referenceCosts: cisternCostSnapshotDto,
      installationReady: z.literal(false),
      positionReserved: z.literal(false),
      limitations: z.array(z.string()),
    }),
  })
  .superRefine(({ snapshot: s }, ctx) => {
    const r = s.request;
    if (
      s.roof.kind !== 'ROOF' ||
      s.ground.kind !== 'GROUND' ||
      [s.roof, s.ground].some((v) => v.districtId !== r.districtId) ||
      s.roof.cellId !== r.roofCellId ||
      s.ground.cellId !== r.groundCellId ||
      s.roof.modelHash !== r.roofModelHash ||
      s.ground.modelHash !== r.groundModelHash ||
      r.captureAreaM2 > s.roof.maxAreaM2 ||
      r.tankAreaM2 > s.ground.maxAreaM2 ||
      Math.abs(s.capacityM3 - r.tankAreaM2 * r.tankDepthM) > 1e-8 ||
      s.referenceCosts.items.length !== 1 ||
      Math.abs(s.referenceCosts.items[0].capacityM3 - s.capacityM3) > 1e-8
    )
      ctx.addIssue({ code: 'custom', message: '이용조 지도 계획의 위치·용량 불일치' });
  });
export type CisternPlanRequest = z.infer<typeof cisternPlanRequestDto>;
export type CisternPlan = z.infer<typeof cisternPlanDto>;
