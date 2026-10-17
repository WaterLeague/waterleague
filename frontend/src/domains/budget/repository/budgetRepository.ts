import { api } from '../../../shared/repository/apiClient';
import { budgetDto } from '../dto/budgetDto';
export const loadBudget = async () => budgetDto.parse(await api<unknown>('/budget'));
