import type { LivePlace } from '../entity/liveUrban';
import { freshReading } from '../service/liveUrbanService';
export function LiveUrbanSource({ places, now }: { places: LivePlace[]; now: number }) {
  return (
    <>
      {' · '}
      <a href="https://data.seoul.go.kr/SeoulRtd/" target="_blank" rel="noreferrer">
        서울 실시간 도시데이터
      </a>
      {' · 121개 공개 장소 경계 내 적용 · 차량 속도는 장소 평균을 이용한 연출'}
      {places.map((place) => {
        const population = freshReading(place.population, now),
          traffic = freshReading(place.traffic, now);
        return (
          <span key={place.id} className="city-live-source">
            {' · '}
            {place.name}
            {population &&
              ` ${population.minimum.toLocaleString('ko-KR')}~${population.maximum.toLocaleString('ko-KR')}명 (${population.sourceHourKst}시대·${population.congestion})`}
            {traffic &&
              ` · 평균 ${traffic.speedKmh}km/h (${new Date(traffic.observedAt).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false })})`}
          </span>
        );
      })}
    </>
  );
}
