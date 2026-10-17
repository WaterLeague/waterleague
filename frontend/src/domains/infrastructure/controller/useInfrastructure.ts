import { useEffect, useState } from 'react';
import type { InfrastructureCatalog } from '../entity/infrastructure';
import { loadInfrastructure } from '../repository/infrastructureRepository';
export function useInfrastructure() {
  const [catalog, setCatalog] = useState<InfrastructureCatalog | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setError(false);
    void loadInfrastructure()
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [revision]);
  return { catalog, error, retry: () => setRevision((v) => v + 1) };
}
