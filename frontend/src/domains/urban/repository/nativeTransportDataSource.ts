import { connectTunnelProfiles } from '../service/nativeTunnelService';
import { readPublicData } from '../../../shared/repository/publicDataCache';
import { nativeTransportDto, nativeTransportIndexDto } from '../dto/nativeTransportDto';
import { CITY_HASH } from '../../city/repository/cityVersion';
export const NATIVE_TRANSPORT_HASH =
  'fcd2a5b2f7e090192ffdd4b691c1294c3ae9be489045cf11c9b2a1010824d098';

export async function readNativeTransport(signal: AbortSignal) {
  const index = nativeTransportIndexDto.parse(
    await readPublicData(
      '/data/seoul-transport-v1/index.json',
      NATIVE_TRANSPORT_HASH,
      65536,
      signal
    )
  );
  if (index.sourceCitySha256 !== CITY_HASH) throw new Error('교통 자료 원본 대응 오류');
  const data = nativeTransportDto.parse(
    await readPublicData(
      '/data/seoul-transport-v1/' + index.file,
      index.sha256,
      index.bytes,
      signal
    )
  );
  if (data.tunnels.length !== (index.counts.tunnels ?? 0)) throw new Error('터널 개수 오류');
  if (data.lanes.length !== index.counts.lanes || data.routes.length !== index.counts.routes)
    throw new Error('교통 자료 개수 오류');
  return { ...data, tunnels: connectTunnelProfiles(data.tunnels) };
}
