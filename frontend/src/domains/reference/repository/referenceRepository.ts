import { api } from '../../../shared/repository/apiClient';
import { mapReference } from '../mapper/referenceMapper';
export async function loadReference() {
  return mapReference(await api('/references'));
}
