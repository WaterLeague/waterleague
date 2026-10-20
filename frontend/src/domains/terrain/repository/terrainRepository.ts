import { z } from 'zod';
import { CityError } from '../../city/exception/CityError';
import type { Terrain } from '../entity/terrain';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const file = z.object({ sha256: sha, bytes: z.number().int().positive().max(1000000) });
const metadata = z.object({
  id: z.literal('seoul-copernicus-dsm-native-90m-v1'),
  width: z.literal(416),
  height: z.literal(340),
  origin: z.tuple([z.number().finite(), z.number().finite()]),
  spacing: z.tuple([z.literal(90), z.literal(-90)]),
  districtIds: z.array(z.string().regex(/^11\d{3}$/)).length(25),
  files: z.object({ 'height-f32le.bin': file, 'district-u8.bin': file, 'cover-u8.bin': file }),
  modelInput: z.literal(false),
});
const ROOT = '/data/seoul-terrain-native-v1/';
let cached: Terrain | null = null;
async function read(file: string, hash: string, signal: AbortSignal, bytes: number) {
  const response = await fetch(ROOT + file, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new CityError('NETWORK');
  const data = await response.arrayBuffer();
  const actual = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))]
    .map((n) => n.toString(16).padStart(2, '0'))
    .join('');
  if (data.byteLength > bytes || actual !== hash) throw new CityError('INVALID_DATA');
  return data;
}
export async function loadTerrain(signal: AbortSignal): Promise<Terrain> {
  if (cached) return cached;
  const raw = await read(
    'terrain.json',
    '020aa06f0ce1eef85c13546c40c5a10ac604fad99b127cb7c9d6c0e58fec9bad',
    signal,
    20000
  );
  const info = metadata.parse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)));
  const files = await Promise.all(
    (['height-f32le.bin', 'district-u8.bin', 'cover-u8.bin'] as const).map((name) =>
      read(name, info.files[name].sha256, signal, info.files[name].bytes)
    )
  );
  const value = {
    ...info,
    heights: new Float32Array(files[0]),
    districts: new Uint8Array(files[1]),
    cover: new Uint8Array(files[2]),
  };
  const count = info.width * info.height;
  if (
    value.heights.length !== count ||
    value.districts.length !== count ||
    value.cover.length !== count ||
    value.cover.some((n) => n > 2) ||
    value.districts.some((n) => n > 25) ||
    value.heights.some((n) => !Number.isFinite(n) || n < -100 || n > 1500)
  )
    throw new CityError('INVALID_DATA');
  if (!signal.aborted) cached = value;
  return value;
}
