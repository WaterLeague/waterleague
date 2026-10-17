import { CloudRain, RefreshCw } from 'lucide-react';
import type { useLiveRainfall } from '../controller/useLiveRainfall';
import { rainCondition } from '../service/rainEffectService';
import './rainfall.css';
const time = (value: string) =>
  new Date(value).toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
  });
export function LiveRainfallPanel({
  districtId,
  rainfall,
}: {
  districtId?: string;
  rainfall: ReturnType<typeof useLiveRainfall>;
}) {
  const { value, busy, error, now, refresh } = rainfall;
  const station = value?.districts.find((d) => d.districtId === districtId);
  const delayed = station?.observedAt
    ? now - Date.parse(station.observedAt) > 300000
    : value
      ? now - Date.parse(value.requestedObservationAt) > 300000
      : false;
  return (
    <section className="live-rainfall" aria-label="기상청 실시간 강우">
      <div className="live-rainfall-heading">
        <span>
          <CloudRain size={17} />
          실시간 강우
        </span>
        <button onClick={() => void refresh()} disabled={busy} aria-label="최신 강우 직접 조회">
          <RefreshCw size={14} />
        </button>
      </div>
      {error ? (
        <p role="alert">{error}</p>
      ) : !value ? (
        <p role="status">기상청에서 직접 조회 중</p>
      ) : (
        <>
          <span className="live-rainfall-status">
            {delayed
              ? '관측 지연'
              : station?.status === 'MISSING'
                ? '관측 결측'
                : '기상청 직접 조회'}{' '}
            · {time(value.requestedObservationAt)} 관측
          </span>
          {station ? (
            <>
              <strong>
                {station.districtName} <small>{station.stationName} 관측소</small>
              </strong>
              <p className="live-rainfall-condition">{rainCondition(station, now)}</p>
              <dl>
                <div>
                  <dt>최근 60분</dt>
                  <dd>
                    {station.sixtyMinuteMm ?? '—'} <small>mm</small>
                  </dd>
                </div>
                <div>
                  <dt>오늘 누적</dt>
                  <dd>
                    {station.dayMm ?? '—'} <small>mm</small>
                  </dd>
                </div>
              </dl>
              <p>최근 1분 {station.oneMinuteMm ?? '—'} mm</p>
              {station.status === 'MISSING' && <p>결측 항목은 0으로 계산하지 않습니다.</p>}
            </>
          ) : (
            <p>
              {value.districts.filter((d) => d.status === 'CURRENT').length}개 구 관측 연결 · 구를
              선택하면 강우량이 표시됩니다.
            </p>
          )}
          <small>
            조회 {time(value.fetchedAt)} · 1분마다 갱신
            <br />
            지점 관측값 · 구 전체의 동일 강우를 뜻하지 않음
          </small>
        </>
      )}
    </section>
  );
}
