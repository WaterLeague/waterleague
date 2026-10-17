import { useEffect, useState } from 'react';
import type { District } from '../entity/district';
import { loadDistricts } from '../repository/districtRepository';

export function useDistricts() {
  const [districts, setDistricts] = useState<District[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    loadDistricts().then(
      (value) => {
        if (active) setDistricts(value);
      },
      () => {
        if (active) setError('지역 목록을 불러오지 못했습니다. 화면을 다시 열어 주세요.');
      }
    );
    return () => {
      active = false;
    };
  }, []);
  return { districts, error };
}
