import { useEffect, useRef, useState } from 'react';
import { LocateFixed, X } from 'lucide-react';
import type { City } from '../entity/city';
import { LocationError } from '../exception/LocationError';
import { currentLocation, type MapLocation } from '../service/currentLocationService';

export function CurrentLocationButton({
  city,
  onLocate,
}: {
  city: City;
  onLocate: (location: MapLocation) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const pending = useRef(false);
  const request = useRef(0);
  useEffect(
    () => () => {
      request.current++;
    },
    []
  );

  async function locate() {
    if (pending.current) return;
    const id = ++request.current;
    pending.current = true;
    setBusy(true);
    setMessage('현재 위치를 확인하고 있습니다.');
    try {
      const location = await currentLocation(city, navigator.geolocation, window.isSecureContext);
      // 브라우저의 위치 요청은 취소할 수 없으므로 화면을 떠난 뒤의 응답은 버린다.
      if (request.current !== id) return;
      onLocate(location);
      setMessage(`${location.districtName}의 현재 위치로 이동했습니다.`);
    } catch (error) {
      if (request.current === id)
        setMessage(
          error instanceof LocationError ? error.message : new LocationError('FAILED').message
        );
    } finally {
      if (request.current === id) {
        pending.current = false;
        setBusy(false);
      }
    }
  }

  return (
    <div className="map-location-control">
      <button
        type="button"
        className="current-location-button"
        onClick={() => void locate()}
        disabled={busy}
        aria-busy={busy}
        title="현재 위치로 이동"
      >
        <LocateFixed size={15} />
        {busy ? '위치 확인 중' : '내 위치'}
      </button>
      {message && (
        <div className="map-location-notice">
          <span role="status">{message}</span>
          <button type="button" onClick={() => setMessage('')} aria-label="위치 안내 닫기">
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
