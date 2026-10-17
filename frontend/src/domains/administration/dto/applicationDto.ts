import { z } from 'zod';
export const applicationDto = z.object({
  id: z.uuid(),
  username: z.string().max(32),
  displayName: z.string().max(40),
  memberType: z.enum(['PLAYER', 'BUSINESS', 'INSTITUTION', 'GOVERNMENT']),
  approvalStatus: z.enum(['PENDING', 'APPROVED', 'REJECTED', 'SUSPENDED']),
  enabled: z.boolean(),
  organizationId: z.uuid().nullable(),
  organizationName: z.string().max(100),
  purpose: z.string().max(2000),
  createdAt: z.iso.datetime({ offset: true }),
});
