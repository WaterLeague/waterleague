import { api } from '../../../shared/repository/apiClient';
import { infrastructureDto } from '../dto/infrastructureDto';
import type { InfrastructureCatalog } from '../entity/infrastructure';
let pending: Promise<InfrastructureCatalog> | null = null;
export function loadInfrastructure() {
  pending ??= api<unknown>('/infrastructure/seoul-public-20261018-v2')
    .then((value) => infrastructureDto.parse(value))
    .catch((error) => {
      pending = null;
      throw error;
    });
  return pending;
}
