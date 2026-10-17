import { api } from '../../../shared/repository/apiClient';
import type { Lab } from '../../game/entity/game';
import type { SearchInput } from '../entity/search';
import { mapSearch, mapSearches } from '../mapper/searchMapper';
import { SearchDataError } from '../exception/SearchDataError';
export function searchRepository(lab: Lab, organizationId: string) {
  return {
    list: async () => mapSearches(await api('/research/searches'), lab.modelHash),
    get: async (id: string) => {
      const value = mapSearch(await api('/research/searches/' + id), lab, organizationId);
      if (value.id !== id) throw new SearchDataError();
      return value;
    },
    create: async (input: SearchInput, key: string) =>
      mapSearch(
        await api('/research/searches', 'POST', {
          jobIds: input.jobIds,
          ...input.settings,
          requestKey: key,
        }),
        lab,
        organizationId,
        input
      ),
  };
}
