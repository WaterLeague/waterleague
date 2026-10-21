import { readPublicData } from '../../../shared/repository/publicDataCache';
import { nativeTransportDto, nativeTransportIndexDto } from '../dto/nativeTransportDto';
import { CITY_HASH } from '../../city/repository/cityVersion';
const HASH = 'e92f6b2fda934969c5bac80a55cc5ce451cb2c78fa3a33242d63523bbd087469';
self.onmessage = async () => {
  try {
    const signal = new AbortController().signal;
    const index = nativeTransportIndexDto.parse(
      await readPublicData('/data/seoul-transport-v1/index.json', HASH, 65536, signal)
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
    if (data.lanes.length !== index.counts.lanes || data.routes.length !== index.counts.routes)
      throw new Error('교통 자료 개수 오류');
    self.postMessage({ data });
  } catch {
    self.postMessage({ failed: true });
  }
};
