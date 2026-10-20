import { z } from 'zod';
import { loadCisternSpecifications } from '../../facility/repository/cisternSpecificationRepository';
import { ApiError } from '../../../shared/exception/ApiError';
import type { CisternPlan } from '../dto/cisternPlanDto';
import { api } from '../../../shared/repository/apiClient';
import { cisternPlanDto, type CisternPlanRequest } from '../dto/cisternPlanDto';
const path = '/installations/cistern-plans';
async function verifySpecifications(plans: CisternPlan[], signal?: AbortSignal) {
  if (plans.some((p) => p.snapshot.equipmentSpecification)) {
    const catalog = await loadCisternSpecifications(signal ?? new AbortController().signal);
    for (const plan of plans) {
      const spec = plan.snapshot.equipmentSpecification;
      if (
        spec &&
        JSON.stringify(spec) !==
          JSON.stringify(catalog.specifications.find((v) => v.id === spec.id))
      )
        throw new ApiError(502, 'INVALID_DATA', '저장한 규격과 공개 원자료가 일치하지 않습니다.');
    }
  }
  return plans;
}
export const loadCisternPlans = async (signal?: AbortSignal) =>
  verifySpecifications(
    z
      .array(cisternPlanDto)
      .max(20)
      .parse(await api<unknown>(path, 'GET', undefined, signal)),
    signal
  );
export const saveCisternPlan = async (request: CisternPlanRequest, signal?: AbortSignal) =>
  (
    await verifySpecifications(
      [cisternPlanDto.parse(await api<unknown>(path, 'POST', request, signal))],
      signal
    )
  )[0];
export const deleteCisternPlan = (id: string, signal?: AbortSignal) =>
  api<void>(`${path}/${encodeURIComponent(id)}`, 'DELETE', undefined, signal);
