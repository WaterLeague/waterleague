import type { DisasterCatalog } from '../../disaster/entity/disaster';
import type { weatherStatus } from '../../rainfall/service/weatherStatus';

const number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });
export function historicalWeather(
  event: DisasterCatalog['events'][number] | undefined,
  index: number,
  districtId: string,
  districtName: string
): ReturnType<typeof weatherStatus> {
  const regions = event?.regions.filter((r) => !districtId || r.districtId === districtId) ?? [];
  const amounts = regions.flatMap((r) => (r.depthsMm[index] == null ? [] : [r.depthsMm[index]]));
  const wet = amounts.filter((n) => n > 0).length;
  const expected = districtId ? 1 : 25;
  const kind = wet ? 'rain' : amounts.length === expected ? 'dry' : 'unknown';
  const min = amounts.length ? Math.min(...amounts) : 0;
  const max = amounts.length ? Math.max(...amounts) : 0;
  return {
    place: districtId ? districtName : '서울 전체',
    kind,
    label: wet
      ? districtId
        ? '비 오는 중'
        : `${wet}개 구 비`
      : kind === 'dry'
        ? '비 없음'
        : '강우 자료 없음',
    amount: amounts.length
      ? `1분 강우 ${number.format(min)}${min === max ? '' : `–${number.format(max)}`} mm${amounts.length < expected ? ` · ${amounts.length}/${expected}개 구` : ''}`
      : '강우량 확인 불가',
    detail:
      districtId && regions[0]
        ? `${regions[0].stationName} AWS · 당시 1분 관측`
        : `${amounts.length}/25개 구 · 당시 1분 관측`,
  };
}
