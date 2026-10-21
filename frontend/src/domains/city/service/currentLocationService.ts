import type { City } from '../entity/city';
import { LocationError } from '../exception/LocationError';
import { viewingDistrict } from './viewingDistrictService';

// 지도 제작과 같은 EPSG:5186 정의로 변환한 뒤 지역 원점을 뺀다.
const projection =
  '+proj=tmerc +lat_0=38 +lon_0=127 +k=1 +x_0=200000 +y_0=600000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs';

export type MapLocation = { center: [number, number]; districtId: string; districtName: string };

export async function seoulLocation(
  city: City,
  { longitude, latitude }: Pick<GeolocationCoordinates, 'longitude' | 'latitude'>
): Promise<MapLocation> {
  if (
    !Number.isFinite(longitude) ||
    !Number.isFinite(latitude) ||
    Math.abs(longitude) > 180 ||
    Math.abs(latitude) > 90
  )
    throw new LocationError('UNAVAILABLE');
  // 변환 라이브러리는 위치 조회에 성공한 경우에만 불러온다.
  const { default: proj4 } = await import('proj4');
  const [east, north] = proj4('EPSG:4326', projection, [longitude, latitude]);
  const center: [number, number] = [
    east - city.originProjected[0],
    north - city.originProjected[1],
  ];
  const district = viewingDistrict(city.districts, center);
  if (!district) throw new LocationError('OUTSIDE_SEOUL');
  return { center, districtId: district.id, districtName: district.name };
}

export async function currentLocation(
  city: City,
  geolocation: Pick<Geolocation, 'getCurrentPosition'> | undefined,
  secure: boolean
): Promise<MapLocation> {
  if (!secure) throw new LocationError('INSECURE');
  if (!geolocation) throw new LocationError('UNSUPPORTED');
  try {
    const position = await new Promise<GeolocationPosition>((resolve, reject) => {
      geolocation.getCurrentPosition(
        resolve,
        (error) =>
          reject(
            new LocationError(
              error.code === 1 ? 'DENIED' : error.code === 3 ? 'TIMEOUT' : 'UNAVAILABLE'
            )
          ),
        { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 }
      );
    });
    return await seoulLocation(city, position.coords);
  } catch (error) {
    if (error instanceof LocationError) throw error;
    throw new LocationError('FAILED');
  }
}
