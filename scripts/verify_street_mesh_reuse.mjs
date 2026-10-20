import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, writeFile, readdir } from "node:fs/promises";
import { once } from "node:events";
import { Worker } from "node:worker_threads";
import { gunzipSync } from "node:zlib";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { createServer } from "../frontend/node_modules/vite/dist/node/index.js";
import {
  BufferGeometry,
  BufferAttribute,
} from "../frontend/node_modules/three/build/three.module.js";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { values } = parseArgs({
  options: { report: { type: "string" }, worker: { type: "boolean" } },
});
assert(values.report);
const hash = (value) => createHash("sha256").update(value).digest("hex");
const base = path.join(root, "frontend/public/data");
const indexRaw = await readFile(path.join(base, "seoul-bridges-v1/index.json"));
const index = JSON.parse(indexRaw);
const packed = await readFile(path.join(base, "seoul-bridges-v1", index.file));
assert.equal(hash(packed), index.storedSha256);
const raw = gunzipSync(packed, { maxOutputLength: index.bytes });
assert.equal(hash(raw), index.sha256);
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
  const bytes = await readFile(
    path.join(base, "seoul-terrain-native-v1", name),
  );
  assert.equal(hash(bytes), entry.sha256);
  files[name] = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  );
}
const terrain = {
  ...info,
  heights: new Float32Array(files["height-f32le.bin"]),
  districts: new Uint8Array(files["district-u8.bin"]),
  cover: new Uint8Array(files["cover-u8.bin"]),
};
const server = await createServer({
  root: path.join(root, "frontend"),
  server: { middlewareMode: true },
  appType: "custom",
});
try {
  const { nativeBridgesDto } = await server.ssrLoadModule(
    "/src/domains/urban/dto/nativeBridgeDto.ts",
  );
  const { NATIVE_BRIDGE_HASH } = await server.ssrLoadModule(
    "/src/domains/urban/repository/nativeBridgeVersion.ts",
  );
  const { nativeStreets } = await server.ssrLoadModule(
    "/src/domains/urban/service/nativeStreetService.ts",
  );
  const { streetGeometry } = await server.ssrLoadModule(
    "/src/domains/urban/service/streetGeometryService.ts",
  );
  const { StreetMeshBuilder } = await server.ssrLoadModule(
    "/src/domains/urban/service/streetMeshService.ts",
  );
  const { partBounds } = await server.ssrLoadModule(
    "/src/shared/repository/meshBounds.ts",
  );
  assert.equal(hash(indexRaw), NATIVE_BRIDGE_HASH);
  const { groups } = nativeBridgesDto.parse(JSON.parse(raw));
  const reference = (roads, detail, center) => {
    const data = streetGeometry(roads, terrain, detail, [], center);
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(data.positions, 3));
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
    const result = {
      ...data,
      normals: geometry.getAttribute("normal").array,
      bounds: partBounds(data.positions, data.ends),
      sphere: [
        ...geometry.boundingSphere.center.toArray(),
        geometry.boundingSphere.radius,
      ],
    };
    geometry.dispose();
    return result;
  };
  const compare = (actual, expected) => {
    for (const name of ["positions", "colors", "normals", "bounds"])
      assert.equal(hash(actual[name]), hash(expected[name]), name + " 불일치");
    assert.deepEqual(actual.ends, expected.ends);
    assert.deepEqual(actual.sphere, expected.sphere);
  };
  if (values.worker) {
    const assets = path.join(root, "frontend/dist/assets");
    const names = (await readdir(assets)).filter((name) =>
      /^streetGeometry\.worker-.*\.js$/.test(name),
    );
    assert.equal(names.length, 1, "검사 전 프론트 배포 빌드 필요");
    const file = path.join(assets, names[0]);
    const source = `
      import { parentPort, workerData } from 'node:worker_threads';
      globalThis.self = globalThis;
      globalThis.postMessage = (message, options) => parentPort.postMessage(message, options?.transfer ?? []);
      await import(workerData.module);
      parentPort.on('message', data => self.onmessage({ data }));
      parentPort.postMessage({ ready: true });
    `;
    const worker = new Worker(
      new URL("data:text/javascript," + encodeURIComponent(source)),
      {
        workerData: { module: pathToFileURL(file).href },
      },
    );
    const receive = () =>
      once(worker, "message", { signal: AbortSignal.timeout(60000) });
    try {
      assert.equal((await receive())[0].ready, true);
      const roads = nativeStreets(
        [],
        groups.filter((g) => g.names?.includes("반포대교")),
      );
      const expected = reference(roads, true);
      const call = async (message, cancel = false) => {
        const result = receive();
        worker.postMessage(message);
        if (cancel) worker.postMessage({ id: message.id, cancel: true });
        const [reply] = await result;
        assert.equal(reply.id, message.id);
        return reply;
      };
      compare(
        (
          await call({
            id: 1,
            roads,
            terrain,
            terrainKey: 1,
            detail: true,
            parkingAisles: [],
          })
        ).data,
        expected,
      );
      compare(
        (
          await call({
            id: 2,
            roads,
            terrainKey: 1,
            detail: true,
            parkingAisles: [],
          })
        ).data,
        expected,
      );
      assert.equal(
        (
          await call({
            id: 3,
            roads,
            terrainKey: 2,
            detail: true,
            parkingAisles: [],
          })
        ).failed,
        true,
      );
      assert.equal(
        (
          await call(
            {
              id: 4,
              roads,
              terrain,
              terrainKey: 2,
              detail: true,
              parkingAisles: [],
            },
            true,
          )
        ).failed,
        true,
      );
      compare(
        (
          await call({
            id: 5,
            roads,
            terrainKey: 2,
            detail: true,
            parkingAisles: [],
          })
        ).data,
        expected,
      );
      const report = {
        schemaVersion: 1,
        status: "PASS",
        bundle: names[0],
        bundleSha256: hash(await readFile(file)),
        indexSha256: hash(indexRaw),
        requests: 5,
        roads: roads.length,
        vertices: expected.positions.length / 3,
        checks: [
          "실제 배포 작업 스레드 실행",
          "버퍼 이전 후 캐시 재사용",
          "미전달 지형 버전 거부",
          "실행 중 취소",
          "취소 뒤 재개",
          "기존 전체 형상·클릭 인덱스 일치",
        ],
        scope:
          "Node 작업 스레드의 실제 배포 계산 코드·메시지 전송 검사. 브라우저 조작·FPS 검증 제외",
      };
      await writeFile(
        path.resolve(values.report),
        JSON.stringify(report, null, 2) + "\n",
        { flag: "wx" },
      );
      console.log(JSON.stringify(report));
    } finally {
      await worker.terminate();
    }
  } else {
    const cases = [];
    for (const name of ["반포대교", "청담대교", "한강대교"]) {
      const group = groups.find((g) => g.names?.includes(name));
      assert(group);
      const center = [
        (group.bounds[0] + group.bounds[2]) / 2,
        (group.bounds[1] + group.bounds[3]) / 2,
      ];
      const selected = groups.filter(
        (g) =>
          g.bounds[0] < center[0] + 2000 &&
          g.bounds[2] > center[0] - 2000 &&
          g.bounds[1] < center[1] + 2000 &&
          g.bounds[3] > center[1] - 2000,
      );
      const roads = nativeStreets([], selected),
        builder = new StreetMeshBuilder();
      const steps = [];
      for (const [dx, dy, detail] of [
        [0, 0, true],
        [500, 0, true],
        [500, 500, true],
        [0, 0, true],
        [0, 0, false],
        [500, 0, false],
      ]) {
        const at = [center[0] + dx, center[1] + dy];
        const cloned = structuredClone(roads);
        const previous = builder.statistics;
        const started = performance.now();
        const actual = await builder.build(
          cloned,
          terrain,
          detail,
          [],
          at,
          new AbortController().signal,
        );
        const incrementalMs = performance.now() - started;
        const referenceStarted = performance.now(),
          expected = reference(roads, detail, at);
        const fullRebuildMs = performance.now() - referenceStarted;
        compare(actual, expected);
        steps.push({
          detail,
          offsetM: [dx, dy],
          fullRebuildMs,
          incrementalMs,
          regenerated: builder.statistics.generated - previous.generated,
          reused: builder.statistics.reused - previous.reused,
          cachedBytes: builder.statistics.bytes,
          vertices: actual.positions.length / 3,
        });
      }
      assert(steps.slice(1).every((step) => step.reused > 0));
      assert.equal(steps.at(-1).regenerated, 0);
      cases.push({ name, groups: selected.length, roads: roads.length, steps });
      console.log(JSON.stringify({ case: name, roads: roads.length, steps }));
    }
    // 모든 육교와 이름이 있는 교량의 상세·축소 형상을 별도로 대조한다.
    const publicGroups = groups.filter(
      (g) => g.role === "PEDESTRIAN_OVERPASS_AREA" || g.names?.length,
    );
    let vertices = 0;
    for (const group of publicGroups) {
      const roads = nativeStreets([], [group]),
        builder = new StreetMeshBuilder();
      for (const detail of [true, false]) {
        const actual = await builder.build(
          roads,
          terrain,
          detail,
          [],
          undefined,
          new AbortController().signal,
        );
        compare(actual, reference(roads, detail));
        vertices += actual.positions.length / 3;
      }
    }
    const report = {
      schemaVersion: 1,
      status: "PASS",
      indexSha256: hash(indexRaw),
      terrainSha256: hash(terrainRaw),
      testedFootbridges: publicGroups.filter(
        (g) => g.role === "PEDESTRIAN_OVERPASS_AREA",
      ).length,
      testedNamedBridgeGroups: publicGroups.filter((g) => g.names?.length)
        .length,
      comparedVertices: vertices,
      cases,
      allGeometryAttributesAndClickIndicesIdentical: true,
      scope:
        "공개 교량·육교와 실제 표시 지형의 CPU 형상 생성 비교. 브라우저 FPS·GPU 업로드·화면 검증 제외",
    };
    await writeFile(
      path.resolve(values.report),
      JSON.stringify(report, null, 2) + "\n",
      { flag: "wx" },
    );
    console.log(JSON.stringify(report));
  }
} finally {
  await server.close();
}
