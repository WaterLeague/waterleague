import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { gunzipSync } from "node:zlib";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";
import { createServer } from "../frontend/node_modules/vite/dist/node/index.js";

const root = fileURLToPath(new URL("../", import.meta.url));
const baseline = process.argv[2] ?? "99b963a831680011a1826ae21f011437490910e9";
assert.match(baseline, /^[a-f0-9]{7,40}$/);
const output = path.resolve(
  root,
  process.argv[3] ?? "output/map-performance-20261021/navigation.json",
);
const originalPath = "frontend/src/domains/urban/service/streetMeshService.ts";
const baselineCode = execFileSync(
  "git",
  ["show", baseline + ":" + originalPath],
  { cwd: root, encoding: "utf8" },
);
const virtual = path.join(
  root,
  path.dirname(originalPath),
  "__navigation_baseline.ts",
);
const server = await createServer({
  root: path.join(root, "frontend"),
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
  plugins: [
    {
      name: "navigation-baseline",
      enforce: "pre",
      resolveId(id) {
        if (id === "/navigation-baseline.ts") return virtual;
      },
      load(id) {
        if (id === virtual) return baselineCode;
      },
    },
  ],
});
const read = async (name) => {
  const raw = await fs.readFile(path.join(root, "frontend/public/data", name));
  return JSON.parse(name.endsWith(".gz") ? gunzipSync(raw) : raw);
};
const sha = (value) => createHash("sha256").update(value).digest("hex");
const signature = (mesh) =>
  sha(
    Buffer.concat(
      ["positions", "colors", "normals", "bounds"]
        .map((key) => Buffer.from(mesh[key].buffer))
        .concat(Buffer.from(JSON.stringify([mesh.ends, mesh.sphere]))),
    ),
  );
const median = (values) =>
  [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
try {
  const module = (name) =>
    server.ssrLoadModule("/src/domains/urban/service/" + name + ".ts");
  const [
    { UrbanRoadBuilder },
    { nativeStreets },
    { nativeRailStreets },
    { connectBridgeDatums },
    { connectTunnelProfiles, attachNativeTunnels, nativeTunnelStreets },
    { StreetMeshBuilder },
    { StreetMeshBuilder: Original },
    { nearbyTiles },
  ] = await Promise.all([
    module("urbanRoadService"),
    module("nativeStreetService"),
    module("nativeTransportService"),
    module("nativeBridgeService"),
    module("nativeTunnelService"),
    module("streetMeshService"),
    server.ssrLoadModule("/navigation-baseline.ts"),
    server.ssrLoadModule("/src/domains/city/service/cityService.ts"),
  ]);
  const [city, raw, transportRaw] = await Promise.all([
    read("seoul-native-v1/city.json"),
    read("seoul-bridges-v1/structures.json.gz"),
    read("seoul-transport-v1/transport.json.gz"),
  ]);
  const bridges = connectBridgeDatums(raw.groups, raw.waterPolygons);
  const transport = {
    ...transportRaw,
    tunnels: connectTunnelProfiles(transportRaw.tunnels),
  };
  const lanes = new Map(transport.lanes.map(([id, n]) => [id, n])),
    widths = new Map(
      transport.lanes.filter((r) => r[2]).map(([id, , w]) => [id, w]),
    );
  const railway = nativeRailStreets(transport, bridges),
    builder = new UrbanRoadBuilder(bridges, transport),
    results = [];
  for (const [name, center] of [
    ["양화대교", [-7035, -3320]],
    ["강남역", [4314, -7713]],
  ]) {
    const entries = nearbyTiles(city, center, 1200);
    const tiles = await Promise.all(
      entries.map(async (e) => ({
        ...(await read("seoul-native-v1/" + e.file)),
        urban: await read("seoul-street-life-v1/tiles/" + e.id + ".json.gz"),
      })),
    );
    const visible = bridges.filter(
      (g) =>
        g.bounds[0] <= center[0] + 1020 &&
        g.bounds[2] >= center[0] - 1020 &&
        g.bounds[1] <= center[1] + 1020 &&
        g.bounds[3] >= center[1] - 1020,
    );
    const nearRail = railway.filter((r) =>
      r.coordinates.some((p, i) => {
        const a = r.coordinates[Math.max(0, i - 1)];
        return (
          Math.min(a[0], p[0]) <= center[0] + 1020 &&
          Math.max(a[0], p[0]) >= center[0] - 1020 &&
          Math.min(a[1], p[1]) <= center[1] + 1020 &&
          Math.max(a[1], p[1]) >= center[1] - 1020
        );
      }),
    );
    const tunnels = transport.tunnels.filter((t) =>
      t.polygons.some((p) =>
        p[0].some((q) => Math.hypot(q[0] - center[0], q[1] - center[1]) < 2000),
      ),
    );
    const beforeStart = performance.now();
    const reference = [
      ...attachNativeTunnels(
        [...nativeStreets(tiles, visible, lanes, widths), ...nearRail],
        tunnels,
      ),
      ...nativeTunnelStreets(tunnels),
    ];
    const formerMainThreadDeriveMs = performance.now() - beforeStart;
    const start = performance.now(),
      roads = builder.build(tiles, center, 1200),
      workerDeriveMs = performance.now() - start;
    assert.ok(
      isDeepStrictEqual(roads, reference),
      "도로·보도·교량·철도·터널 전체 필드 일치",
    );
    assert.equal(
      builder.build(tiles, center, 1200),
      roads,
      "같은 시야 자료 재사용",
    );
    const oldMesh = new Original(),
      newMesh = new StreetMeshBuilder(),
      signal = new AbortController().signal;
    const retained = structuredClone(roads);
    const originalFirstAt = performance.now();
    const oldFirst = await oldMesh.build(
      structuredClone(roads),
      null,
      true,
      [],
      center,
      signal,
    );
    const originalFirstMs = performance.now() - originalFirstAt;
    const optimizedFirstAt = performance.now();
    const newFirst = await newMesh.build(
      retained,
      null,
      true,
      [],
      center,
      signal,
    );
    const optimizedFirstMs = performance.now() - optimizedFirstAt;
    assert.equal(signature(oldFirst), signature(newFirst));
    const originalMs = [],
      optimizedMs = [],
      geometry = [];
    for (let pass = 0; pass < 3; pass++) {
      const focus = [center[0] + (pass % 2) * 500, center[1]];
      const t = performance.now();
      const a = await oldMesh.build(
        structuredClone(roads),
        null,
        true,
        [],
        focus,
        signal,
      );
      originalMs.push(performance.now() - t);
      const u = performance.now();
      const b = await newMesh.build(retained, null, true, [], focus, signal);
      optimizedMs.push(performance.now() - u);
      assert.equal(
        signature(a),
        signature(b),
        "차선·난간·색·법선·클릭 순서·경계 일치",
      );
      geometry.push({ vertices: b.positions.length / 3, sha256: signature(b) });
    }
    results.push({
      name,
      center,
      distance: 1200,
      tiles: entries.map((e) => ({ id: e.id, sha256: e.sha256 })),
      roads: roads.length,
      railTraffic: builder.railTraffic.length,
      formerMainThreadDeriveMs,
      workerDeriveMs,
      originalFirstMs,
      optimizedFirstMs,
      originalMs,
      optimizedMs,
      originalMedianMs: median(originalMs),
      optimizedMedianMs: median(optimizedMs),
      geometry,
    });
  }
  const sourceFiles = [
    originalPath,
    "frontend/src/domains/urban/service/urbanRoadService.ts",
    "frontend/src/domains/urban/service/railLifeService.ts",
    "frontend/src/domains/urban/service/nativeBridgeService.ts",
    "frontend/src/domains/urban/service/nativeStreetService.ts",
    "frontend/src/domains/urban/service/streetGeometryService.ts",
    "frontend/public/data/seoul-native-v1/city.json",
    "frontend/public/data/seoul-bridges-v1/index.json",
    "frontend/public/data/seoul-transport-v1/index.json",
  ];
  const sourceHashes = Object.fromEntries(
    await Promise.all(
      sourceFiles.map(async (file) => [
        file,
        sha(await fs.readFile(path.join(root, file))),
      ]),
    ),
  );
  const report = {
    sourceHashes,
    schemaVersion: 1,
    baselineCommit: baseline,
    measuredAt: new Date().toISOString(),
    runtime: process.version,
    cpu: os.cpus()[0].model,
    scope:
      "실제 공개 원형 자료의 도로 파생 전체 필드 및 CPU 메시/복제 비교. 지형 null. 네트워크·브라우저 FPS·GPU 완료 시간과 구분",
    elementsReduced: false,
    results,
  };
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
} finally {
  await server.close();
}
