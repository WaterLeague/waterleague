import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { readFile, writeFile, readdir } from "node:fs/promises";
import { Worker } from "node:worker_threads";
import { gunzipSync } from "node:zlib";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { createServer } from "../frontend/node_modules/vite/dist/node/index.js";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { values } = parseArgs({
  options: {
    report: { type: "string" },
    worker: { type: "boolean" },
    all: { type: "boolean" },
  },
});
assert(values.report, "--report 필요");
const hash = (value) => createHash("sha256").update(value).digest("hex");
const base = path.join(root, "frontend/public/data");
const server = await createServer({
  root: path.join(root, "frontend"),
  server: { middlewareMode: true },
  appType: "custom",
});
const signal = () => new AbortController().signal;
const compare = (actual, expected) => {
  for (const name of ["positions", "normals", "bounds"]) {
    assert(actual[name].every(Number.isFinite), `${name} 비유한 값`);
    assert.equal(hash(actual[name]), hash(expected[name]), `${name} 불일치`);
  }
  assert.deepEqual(actual.ends, expected.ends);
};
try {
  const { CITY_HASH } = await server.ssrLoadModule(
    "/src/domains/city/repository/cityRepository.ts",
  );
  const { mapCity, mapCityTile } = await server.ssrLoadModule(
    "/src/domains/city/mapper/cityMapper.ts",
  );
  const { buildBuildingMesh } = await server.ssrLoadModule(
    "/src/domains/city/service/buildingGeometryService.ts",
  );
  const { BuildingMeshBuilder } = await server.ssrLoadModule(
    "/src/domains/city/service/buildingMeshService.ts",
  );
  const { buildingBaseElevation } = await server.ssrLoadModule(
    "/src/domains/city/service/buildingElevationService.ts",
  );
  const cityRaw = await readFile(path.join(base, "seoul-native-v1/city.json"));
  assert.equal(hash(cityRaw), CITY_HASH);
  const city = mapCity(JSON.parse(cityRaw));
  const terrainRaw = await readFile(
    path.join(base, "seoul-terrain-native-v1/terrain.json"),
  );
  assert.equal(
    hash(terrainRaw),
    "020aa06f0ce1eef85c13546c40c5a10ac604fad99b127cb7c9d6c0e58fec9bad",
  );
  const info = JSON.parse(terrainRaw),
    files = {};
  for (const [name, entry] of Object.entries(info.files)) {
    const raw = await readFile(
      path.join(base, "seoul-terrain-native-v1", name),
    );
    assert.equal(hash(raw), entry.sha256);
    assert.equal(raw.length, entry.bytes);
    files[name] = raw.buffer.slice(
      raw.byteOffset,
      raw.byteOffset + raw.byteLength,
    );
  }
  const terrain = {
    ...info,
    heights: new Float32Array(files["height-f32le.bin"]),
    districts: new Uint8Array(files["district-u8.bin"]),
    cover: new Uint8Array(files["cover-u8.bin"]),
  };
  const readTile = async (entry) => {
    const packed = await readFile(
      path.join(base, "seoul-native-v1", entry.file),
    );
    assert.equal(packed.length, entry.storedBytes);
    assert.equal(hash(packed), entry.storedSha256);
    const raw = gunzipSync(packed, { maxOutputLength: entry.bytes });
    assert.equal(raw.length, entry.bytes);
    assert.equal(hash(raw), entry.sha256);
    const tile = mapCityTile(JSON.parse(raw), entry.id, entry.buildingCount);
    return tile.buildings.map((b) => ({
      ...b,
      baseElevationM: buildingBaseElevation(terrain, b.polygons),
    }));
  };
  const entries = [...city.tiles]
    .sort((a, b) => b.buildingCount - a.buildingCount)
    .slice(0, 2);
  const buildings = (await Promise.all(entries.map(readTile)))
    .flat()
    .slice(0, 6000);
  assert.equal(buildings.length, 6000);
  const report = {
    schemaVersion: 1,
    status: "PASS",
    sourceCitySha256: CITY_HASH,
    sourceTerrainSha256: hash(terrainRaw),
    sourceTiles: entries.map(({ id, sha256 }) => ({ id, sha256 })),
    buildingCount: buildings.length,
    node: process.version,
    platform: process.platform,
    arch: process.arch,
    allGeometryAttributesAndClickIndicesIdentical: true,
  };
  if (values.worker) {
    const assets = path.join(root, "frontend/dist/assets");
    const names = (await readdir(assets)).filter((name) =>
      /^buildingGeometry\.worker-.*\.js$/.test(name),
    );
    assert.equal(names.length, 1, "검사 전 배포 빌드 필요");
    const file = path.join(assets, names[0]);
    const adapter = `
      import { parentPort, workerData } from 'node:worker_threads';
      globalThis.self = globalThis;
      globalThis.postMessage = (message, options) => parentPort.postMessage(message, options?.transfer ?? []);
      await import(workerData.module);
      parentPort.on('message', data => self.onmessage({ data }));
      parentPort.postMessage({ ready: true });
    `;
    const worker = new Worker(
      new URL("data:text/javascript," + encodeURIComponent(adapter)),
      {
        workerData: { module: pathToFileURL(file).href },
      },
    );
    const receive = () =>
      once(worker, "message", { signal: AbortSignal.timeout(60000) });
    try {
      assert.equal((await receive())[0].ready, true);
      const call = async (message, cancel = false) => {
        const result = receive();
        worker.postMessage(message);
        if (cancel) worker.postMessage({ id: message.id, cancel: true });
        const [reply] = await result;
        assert.equal(reply.id, message.id);
        return reply;
      };
      const expected = buildBuildingMesh(buildings);
      compare((await call({ id: 1, buildings })).data, expected);
      compare((await call({ id: 2, buildings })).data, expected);
      compare(
        (await call({ id: 3, buildings: buildings.slice(1) })).data,
        buildBuildingMesh(buildings.slice(1)),
      );
      assert.equal((await call({ id: 4, buildings }, true)).failed, true);
      compare((await call({ id: 5, buildings })).data, expected);
      assert.equal((await call({ id: 6, buildings: null })).failed, true);
      compare((await call({ id: 7, buildings })).data, expected);
      Object.assign(report, {
        bundle: names[0],
        bundleSha256: hash(await readFile(file)),
        requests: 7,
        checks: [
          "배포 Worker 실행",
          "버퍼 전송 후 재사용",
          "건물 묶음 변경",
          "취소 후 재개",
          "잘못된 요청 후 복구",
          "형상·선택 범위 동일",
        ],
        scope:
          "Node 작업 스레드의 실제 배포 코드·메시지/버퍼 전송 검사. 브라우저 조작·FPS·GPU 검증 제외",
      });
    } finally {
      await worker.terminate();
    }
  } else {
    const builder = new BuildingMeshBuilder();
    const coldStart = performance.now();
    const cold = await builder.build(buildings, signal());
    report.coldMs = performance.now() - coldStart;
    compare(cold, buildBuildingMesh(buildings));
    const directTimes = [],
      reusedTimes = [],
      samples = [];
    for (let pass = 0; pass < 5; pass++) {
      // 실제 설치 상태를 바꾸지 않고 표시 묶음에서 건물 한 개가 이동하는 경우를 재현한다.
      const groups = [buildings.slice(1 + pass), buildings.slice(0, 1 + pass)];
      const cloned = structuredClone(groups);
      const previous = builder.statistics;
      let expected, actual, directMs, reusedMs;
      const direct = () => {
        const start = performance.now();
        expected = groups.map(buildBuildingMesh);
        directMs = performance.now() - start;
      };
      const reuse = async () => {
        const start = performance.now();
        actual = [];
        for (const group of cloned)
          actual.push(await builder.build(group, signal()));
        reusedMs = performance.now() - start;
      };
      if (pass % 2) {
        await reuse();
        direct();
      } else {
        direct();
        await reuse();
      }
      actual.forEach((data, i) => compare(data, expected[i]));
      const generated = builder.statistics.generated - previous.generated;
      const reused = builder.statistics.reused - previous.reused;
      assert.equal(generated, 0);
      assert.equal(reused, buildings.length);
      assert(builder.statistics.bytes <= 32 * 1024 * 1024);
      directTimes.push(directMs);
      reusedTimes.push(reusedMs);
      samples.push({
        directMs,
        reusedMs,
        generated,
        reused,
        cachedBytes: builder.statistics.bytes,
      });
    }
    const median = (numbers) =>
      [...numbers].sort((a, b) => a - b)[Math.floor(numbers.length / 2)];
    Object.assign(report, {
      samples,
      fullRebuildMedianMs: median(directTimes),
      reusedMedianMs: median(reusedTimes),
      scope:
        "공개 서울 건물과 표시 지형의 CPU 생성·재사용 비교. 표시 묶음 변경은 시험용이며 실제 설치·브라우저 FPS·GPU 업로드 검증 제외",
    });
    if (values.all) {
      const districts = {},
        checkedTiles = [],
        aggregate = createHash("sha256");
      let count = 0;
      for (const entry of city.tiles) {
        const rows = await readTile(entry);
        const actual = await new BuildingMeshBuilder().build(rows, signal());
        const expected = buildBuildingMesh(rows);
        compare(actual, expected);
        for (const name of ["positions", "normals", "bounds"])
          aggregate.update(actual[name]);
        aggregate.update(JSON.stringify(actual.ends));
        for (const row of rows)
          districts[row.districtId] = (districts[row.districtId] ?? 0) + 1;
        count += rows.length;
        checkedTiles.push({
          id: entry.id,
          sha256: entry.sha256,
          buildings: rows.length,
        });
        if (checkedTiles.length % 100 === 0)
          console.log(
            JSON.stringify({
              checkedTiles: checkedTiles.length,
              buildings: count,
            }),
          );
      }
      assert.equal(count, city.buildingCount);
      assert.equal(Object.keys(districts).length, 25);
      report.fullSourceComparison = {
        buildings: count,
        tiles: checkedTiles.length,
        districts,
        aggregateGeometrySha256: aggregate.digest("hex"),
        checkedTiles,
      };
    }
  }
  report.sourceHashes = Object.fromEntries(
    await Promise.all(
      [
        "scripts/verify_building_mesh_reuse.mjs",
        "frontend/src/domains/city/service/buildingMeshService.ts",
        "frontend/src/domains/city/service/buildingGeometryService.ts",
        "frontend/src/domains/city/service/buildingGeometry.worker.ts",
        "frontend/src/domains/city/service/buildingMeshCache.ts",
        "frontend/src/domains/city/repository/buildingGeometryRepository.ts",
        "frontend/pnpm-lock.yaml",
      ].map(async (name) => [
        name,
        hash(await readFile(path.join(root, name))),
      ]),
    ),
  );
  await writeFile(
    path.resolve(values.report),
    JSON.stringify(report, null, 2) + "\n",
    { flag: "wx" },
  );
  console.log(
    JSON.stringify({
      ...report,
      sourceHashes: undefined,
      fullSourceComparison: report.fullSourceComparison && {
        ...report.fullSourceComparison,
        checkedTiles: undefined,
      },
    }),
  );
} finally {
  await server.close();
}
