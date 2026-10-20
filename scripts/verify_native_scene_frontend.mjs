import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { gunzipSync } from 'node:zlib';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { values } = parseArgs({ options: { report: { type: 'string' } } });
assert(values.report, '--report 필요');
const reportPath = path.resolve(values.report);
assert.equal(await lstat(reportPath).then(() => true, (e) => {
  if (e.code !== 'ENOENT') throw e;
  return false;
}), false, '기존 검증 결과 덮어쓰기 금지');
const hash = (raw) => createHash('sha256').update(raw).digest('hex');
const hashFile = async (name) => {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(name)) digest.update(chunk);
  return digest.digest('hex');
};
const sources = ['scripts/verify_native_scene_frontend.mjs', 'scripts/package_native_scene.py',
  'frontend/src/domains/city/dto/cityDto.ts', 'frontend/src/domains/city/mapper/cityMapper.ts',
  'frontend/src/domains/city/repository/cityRepository.ts', 'frontend/src/shared/repository/publicDataCache.ts',
  'frontend/pnpm-lock.yaml'];
const sourceHashes = Object.fromEntries(await Promise.all(sources.map(async (name) => [name, await hashFile(path.join(root, name))])));
const read = async (name, maximum, expected) => {
  const info = await lstat(name);
  assert(info.isFile() && !info.isSymbolicLink() && info.size <= maximum, '자료 경로·크기 제한');
  const raw = await readFile(name);
  if (expected) assert.equal(hash(raw), expected, '원문 해시 불일치');
  return raw;
};
const sceneDirectory = path.join(root, 'data/private/vworld-seoul-topography-20260307/scene-v1');
const output = path.join(root, 'frontend/public/data/seoul-native-v1');
const spatialSha = '4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7';
const sceneSha = '7af763a751b8d697ab0f0c7d09aaab3efe724c89bebc46f7ddaf9c565a48910a';
const databasePath = path.join(root, 'tmp/native-spatial', spatialSha, 'play.sqlite');
assert.equal(await hashFile(databasePath), spatialSha);
const database = new DatabaseSync(databasePath, { readOnly: true });
database.exec('PRAGMA trusted_schema=OFF; PRAGMA query_only=ON; PRAGMA cache_size=-8192');
const candidate = database.prepare('SELECT body,allowed_mask FROM sites WHERE object_id=?');
const server = await createServer({ root: path.join(root, 'frontend'), server: { middlewareMode: true }, appType: 'custom' });
try {
  const { CITY_HASH } = await server.ssrLoadModule('/src/domains/city/repository/cityRepository.ts');
  const { mapCity, mapCityTile } = await server.ssrLoadModule('/src/domains/city/mapper/cityMapper.ts');
  const city = mapCity(JSON.parse(await read(path.join(output, 'city.json'), 16 * 1024 ** 2, CITY_HASH)));
  const scene = JSON.parse(await read(path.join(sceneDirectory, 'catalog.json'), 16 * 1024 ** 2, sceneSha));
  assert.equal(city.siteCatalogSha256, spatialSha);
  assert.equal(city.tiles.length, scene.tiles.length);
  assert.deepEqual(city.originProjected, scene.originProjected);
  const originals = new Map(scene.tiles.map((tile) => [tile.id, tile]));
  const identifiers = new Set();
  let buildings = 0, features = 0, candidates = 0, roofCandidates = 0, groundCandidates = 0, rawBytes = 0;
  const roles = {};
  function projected(display, original, depth = 0) {
    assert.equal(display.length, original.length, '원 도형의 구멍·구성·정점 수 불일치');
    if (typeof display[0] === 'number') {
      assert.equal(display.length, 2);
      assert(Math.abs(display[0] + city.originProjected[0] - original[0]) <= 1e-8);
      assert(Math.abs(display[1] + city.originProjected[1] - original[1]) <= 1e-8);
    } else {
      assert(depth < 5);
      for (let i = 0; i < display.length; i++) projected(display[i], original[i], depth + 1);
    }
  }
  for (const [index, entry] of city.tiles.entries()) {
    const sourceEntry = originals.get(entry.id);
    assert(sourceEntry && /^tiles\/-?\d+_-?\d+\.json$/.test(sourceEntry.file));
    const sourceTile = JSON.parse(await read(path.join(sceneDirectory, sourceEntry.file), sourceEntry.bytes, sourceEntry.sha256));
    const packed = await read(path.join(output, entry.file), entry.storedBytes, entry.storedSha256);
    assert.equal(packed.length, entry.storedBytes);
    const raw = gunzipSync(packed, { maxOutputLength: entry.bytes });
    assert.equal(raw.length, entry.bytes);
    assert.equal(hash(raw), entry.sha256);
    const tile = mapCityTile(JSON.parse(raw), entry.id, entry.buildingCount);
    assert.equal(tile.nativeFeatures.length, entry.featureCount);
    assert.equal(tile.buildings.length + tile.nativeFeatures.length, sourceTile.features.length);
    const byId = new Map(sourceTile.features.map((feature) => [feature.id, feature]));
    for (const feature of [...tile.buildings, ...tile.nativeFeatures]) {
      assert(!identifiers.has(feature.id), '타일 간 원 객체 중복');
      identifiers.add(feature.id);
      const original = byId.get(feature.id);
      assert(original, '원 객체 누락');
      assert.equal(feature.districtId, original.districtId);
      assert.equal(feature.geometryEligibility, original.geometryEligibility);
      assert.deepEqual(feature.center, original.center);
      roles[original.role] = (roles[original.role] ?? 0) + 1;
      const geometry = original.geometry;
      if ('polygons' in feature) {
        assert.equal(original.role, 'BUILDING_FOOTPRINT');
        assert.deepEqual(feature.polygons, geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates);
        assert.equal(feature.areaM2, original.sourceAreaM2);
        assert.equal(feature.heightM, original.heightM);
        assert.equal(feature.heightSource, original.heightBasis);
      } else {
        for (const key of ['role', 'geometry', 'sourceAreaM2', 'sourceLengthM']) assert.deepEqual(feature[key], original[key]);
      }
      const row = candidate.get(feature.id);
      const cell = row && JSON.parse(row.body);
      const expectedId = row?.allowed_mask ? cell.id : null;
      assert.equal(feature.candidateId, expectedId);
      if (expectedId) {
        assert.equal(cell.role, original.role);
        if (cell.kind === 'ROOF') {
          assert.equal(cell.districtId, feature.districtId);
          assert.equal(cell.areaM2, original.sourceAreaM2);
          assert.equal(cell.geometry.type, geometry.type);
          projected(geometry.coordinates, cell.geometry.coordinates);
          roofCandidates++;
        } else {
          // 지상 후보는 원면에서 공개 제외 영역을 뺀 별도 파생 도형이다.
          assert(cell.areaM2 <= original.sourceAreaM2 + 1e-7);
          assert.equal(feature.allowedMask, row.allowed_mask);
          groundCandidates++;
        }
        candidates++;
      }
    }
    buildings += tile.buildings.length;
    features += tile.nativeFeatures.length;
    rawBytes += raw.length;
    if ((index + 1) % 100 === 0) console.log(JSON.stringify({ tiles: index + 1, total: city.tiles.length }));
  }
  assert.equal(buildings, city.buildingCount);
  assert.deepEqual(roles, scene.counts);
  assert.equal(candidates, database.prepare('SELECT COUNT(*) AS count FROM sites WHERE allowed_mask<>0').get().count);
  assert.equal(await hashFile(databasePath), spatialSha);
  for (const [name, expected] of Object.entries(sourceHashes))
    assert.equal(await hashFile(path.join(root, name)), expected, '검사 중 코드 변경');
  const report = { schemaVersion: 1, status: 'PASS', citySha256: CITY_HASH, sceneSha256: sceneSha,
    spatialSha256: spatialSha, tileCount: city.tiles.length, buildingCount: buildings, featureCount: features,
    candidateCount: candidates, roofCandidateCount: roofCandidates, groundCandidateCount: groundCandidates,
    rawTileBytes: rawBytes, sourceHashes, versions: { node: process.version },
    fullSourceGeometryMatched: true, roofCandidateGeometryMatched: true, groundCandidateIdsMatched: true,
    groundCandidateGeometryCompared: false, coordinateToleranceM: 1e-8,
    browserPerformanceVerified: false, fieldValidation: false };
  await writeFile(reportPath, JSON.stringify(report) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ status: 'PASS', tiles: city.tiles.length, buildings, features, candidates }));
} finally {
  database.close();
  await server.close();
}
