import { z } from 'zod';
import { applicationDto } from '../dto/applicationDto';
import { ApprovalDataError } from '../exception/ApprovalDataError';
export function mapApplications(value: unknown) {
  const parsed = z.array(applicationDto).max(100).safeParse(value);
  if (!parsed.success) throw new ApprovalDataError();
  return parsed.data;
}
