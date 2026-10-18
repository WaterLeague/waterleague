import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { cisternPlanDto, type CisternPlanRequest } from '../dto/cisternPlanDto';
const path = '/installations/cistern-plans';
export const loadCisternPlans = async (signal?: AbortSignal) =>
  z
    .array(cisternPlanDto)
    .max(20)
    .parse(await api<unknown>(path, 'GET', undefined, signal));
export const saveCisternPlan = async (request: CisternPlanRequest, signal?: AbortSignal) =>
  cisternPlanDto.parse(await api<unknown>(path, 'POST', request, signal));
export const deleteCisternPlan = (id: string, signal?: AbortSignal) =>
  api<void>(`${path}/${encodeURIComponent(id)}`, 'DELETE', undefined, signal);
