import { useState, useEffect } from 'react';
import type { District, AffiliationType } from '../entity/district';
import { loadDistricts } from '../repository/districtRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
export function DistrictFields({
  districtId,
  affiliationType,
  onDistrict,
  onType,
}: {
  districtId: string;
  affiliationType: AffiliationType;
  onDistrict: (id: string) => void;
  onType: (type: AffiliationType) => void;
}) {
  const [districts, setDistricts] = useState<District[]>([]),
    [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setError('');
    void loadDistricts()
      .then((v) => {
        if (alive) setDistricts(v);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [attempt]);
  return (
    <>
      <label>
        참여 방식
        <select value={affiliationType} onChange={(e) => onType(e.target.value as AffiliationType)}>
          <option value="RESIDENT">서울 거주 · 거주 구로 참여</option>
          <option value="AFFILIATED">비거주 · 원하는 구로 참여</option>
        </select>
      </label>
      <label>
        소속 구
        <select required value={districtId} onChange={(e) => onDistrict(e.target.value)}>
          <option value="">25개 구 중 선택</option>
          {districts.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p role="alert">
          {error}{' '}
          <button type="button" onClick={() => setAttempt((v) => v + 1)}>
            다시 조회
          </button>
        </p>
      )}
      <p className="footnote">
        선택한 구에만 시설을 설치할 수 있습니다. 상세 주소는 받지 않으며 소속 구는 가입 후 변경할 수
        없습니다.
      </p>
    </>
  );
}
