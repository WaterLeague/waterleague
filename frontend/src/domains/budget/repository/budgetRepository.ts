import { competitionScope } from '../../competition/repository/competitionScope';
import { api } from '../../../shared/repository/apiClient';
import { budgetDto, budgetLedgerDto } from '../dto/budgetDto';
export const loadBudget = async (competitionId?: string | null) =>
  budgetDto.parse(await api<unknown>(competitionScope('/budget', competitionId)));
export const loadBudgetLedger = async (beforeId?: string, signal?: AbortSignal) =>
  budgetLedgerDto.parse(
    await api<unknown>(
      `/budget/ledger${beforeId ? `?beforeId=${encodeURIComponent(beforeId)}` : ''}`,
      'GET',
      undefined,
      signal
    )
  );
