import { useEffect, useState } from 'react';
import type { EquipmentHistoryCatalog } from '../dto/equipmentHistoryDto';
import { loadEquipmentHistory } from '../repository/equipmentHistoryRepository';

export function useEquipmentHistory(eventId: string) {
  const [state, setState] = useState<{
    key: string;
    value: EquipmentHistoryCatalog | null;
    error: boolean;
  }>();
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void loadEquipmentHistory(eventId).then(
      (value) => {
        if (active) setState({ key: eventId, value, error: false });
      },
      () => {
        if (active) setState({ key: eventId, value: null, error: true });
      }
    );
    return () => {
      active = false;
    };
  }, [eventId, revision]);
  return {
    value: state?.key === eventId ? state.value : null,
    error: state?.key === eventId && state.error,
    retry: () => setRevision((v) => v + 1),
  };
}
