import { z } from 'zod';
import { readPublicData } from '../../../shared/repository/publicDataCache';
import { CityError } from '../../city/exception/CityError';
import { CITY_HASH } from '../../city/repository/cityVersion';
import { nativeBridgesDto } from '../dto/nativeBridgeDto';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const indexDto = z.object({
  schemaVersion: z.literal(1),
  id: z.literal('SEOUL_NGII_BRIDGES_V1'),
  sourceCitySha256: sha,
  sourceSpatialSha256: sha,
  file: z.literal('structures.json.gz'),
  sha256: sha,
  bytes: z.number().int().positive().max(64000000),
  counts: z.object({
    sourceObjects: z.number().int().positive(),
    groups: z.number().int().positive().max(10000),
    profiles: z.number().int().nonnegative(),
  }),
  policy: z.object({
    displayOnly: z.literal(true),
    sourcePolygonsUnchanged: z.literal(true),
    hydraulicInputsChanged: z.literal(false),
    approachClip: z.literal('SOURCE_TRANSPORT_AREA'),
    connections: z.literal('SOURCE_ENDPOINTS_ONLY'),
  }),
});
import { NATIVE_BRIDGE_HASH } from './nativeBridgeVersion';
export async function readNativeBridges(signal: AbortSignal) {
  const index = indexDto.safeParse(
    await readPublicData('/data/seoul-bridges-v1/index.json', NATIVE_BRIDGE_HASH, 524288, signal)
  );
  if (!index.success || index.data.sourceCitySha256 !== CITY_HASH)
    throw new CityError('INVALID_DATA');
  const body = nativeBridgesDto.safeParse(
    await readPublicData(
      '/data/seoul-bridges-v1/' + index.data.file,
      index.data.sha256,
      index.data.bytes,
      signal
    )
  );
  if (
    !body.success ||
    body.data.groups.length !== index.data.counts.groups ||
    body.data.groups.reduce((sum, g) => sum + g.sourceIds.length, 0) !==
      index.data.counts.sourceObjects
  )
    throw new CityError('INVALID_DATA');
  return body.data.groups;
}
