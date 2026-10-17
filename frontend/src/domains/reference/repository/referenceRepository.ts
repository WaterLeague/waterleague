import { api } from '../../../shared/repository/apiClient';
import { mapReference } from '../mapper/referenceMapper';
export async function loadReference(modelHash: string) {
  return mapReference(
    await api('/references?modelHash=' + encodeURIComponent(modelHash)),
    modelHash
  );
}
