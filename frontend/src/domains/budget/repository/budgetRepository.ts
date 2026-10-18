import { api } from '../../../shared/repository/apiClient';
import { budgetDto, budgetLedgerDto } from '../dto/budgetDto';
export const loadBudget = async () => budgetDto.parse(await api<unknown>('/budget'));
export const loadBudgetLedger = async (beforeId?: string, signal?: AbortSignal) =>
  budgetLedgerDto.parse(
    await api<unknown>(
      `/budget/ledger${beforeId ? `?beforeId=${encodeURIComponent(beforeId)}` : ''}`,
      'GET',
      undefined,
      signal
    )
  );
