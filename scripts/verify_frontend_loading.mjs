import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { dirname, resolve, relative } from "node:path";
import { build } from "../frontend/node_modules/vite/dist/node/index.js";

const root = resolve(import.meta.dirname, "..");
const output = process.argv[2];
assert(output, "검증 기록의 출력 경로 필요");
const result = await build({
  root: `${root}/frontend`,
  logLevel: "warn",
  build: { write: false, reportCompressedSize: false },
});
assert(!Array.isArray(result) && "output" in result);
const chunks = result.output.filter((item) => item.type === "chunk");
const entry = chunks.find(
  (item) =>
    item.isEntry && item.facadeModuleId === `${root}/frontend/index.html`,
);
assert(entry, "앱 진입 파일 누락");
const byName = new Map(chunks.map((item) => [item.fileName, item]));
function closure(initial) {
  const found = new Set();
  function visit(name) {
    if (found.has(name)) return;
    const chunk = byName.get(name);
    assert(chunk, `의존 파일 누락: ${name}`);
    found.add(name);
    chunk.imports.forEach(visit);
  }
  initial.forEach(visit);
  return [...found];
}
const initial = closure([entry.fileName]);
const renderer =
  /\/(?:@react-three\/|react-reconciler\/)|\/three\/build\/three\.module\.js$/;
const initialRendererModules = initial.flatMap((name) =>
  Object.entries(byName.get(name).modules)
    .filter(([id, value]) => value.renderedLength > 0 && renderer.test(id))
    .map(([id]) => relative(root, id)),
);
const scene = chunks.find((item) =>
  item.facadeModuleId?.endsWith("/city/view/CityScene.tsx"),
);
assert(scene, "3D 화면의 별도 로딩 파일 누락");
const rows = chunks.map((chunk) => ({
  file: chunk.fileName,
  bytes: Buffer.byteLength(chunk.code),
  gzipBytes: gzipSync(chunk.code).length,
  sha256: createHash("sha256").update(chunk.code).digest("hex"),
  initial: initial.includes(chunk.fileName),
  imports: chunk.imports,
  dynamicImports: chunk.dynamicImports,
  modules: Object.entries(chunk.modules)
    .filter(([, value]) => value.renderedLength > 0)
    .map(([id]) => relative(root, id)),
}));
const initialRows = rows.filter((row) => row.initial);
const sceneFiles = closure([scene.fileName]);
const initialModules = new Set(initialRows.flatMap((row) => row.modules));
const sceneModules = new Set(
  rows
    .filter((row) => sceneFiles.includes(row.file))
    .flatMap((row) => row.modules),
);
const layers = [
  [
    "infrastructure/view/InfrastructureFootprintsPlan.tsx",
    "infrastructure/view/InfrastructureFootprints.tsx",
  ],
  ["floodtrace/view/FloodTracePlan.tsx", "floodtrace/view/FloodTraceLayer.tsx"],
  ["surface/view/SurfacePlan.tsx", "surface/view/SurfaceLayer.tsx"],
].map(([plan, scene]) => ({
  plan,
  scene,
  planInitiallyAvailable: initialModules.has(`frontend/src/domains/${plan}`),
  sceneDeferred:
    !initialModules.has(`frontend/src/domains/${scene}`) &&
    sceneModules.has(`frontend/src/domains/${scene}`),
}));
const sceneRendererModules = [...sceneModules].filter((id) =>
  renderer.test("/" + id),
);
const report = {
  schemaVersion: 1,
  scope: "PRODUCTION_MODULE_GRAPH_NOT_NETWORK_TIMING_OR_BROWSER_FPS",
  initialDefinition:
    "HTML_ENTRY_STATIC_IMPORT_CLOSURE_EXCLUDING_DYNAMIC_MAP_PRELOAD",
  nodeVersion: process.version,
  gzipMethod: "NODE_ZLIB_GZIP_SYNC_DEFAULT_LEVEL_6_NOT_SERVER_TRANSFER_MEASUREMENT",
  initialJsBytes: initialRows.reduce((sum, row) => sum + row.bytes, 0),
  initialGzipBytes: initialRows.reduce((sum, row) => sum + row.gzipBytes, 0),
  allJsBytes: rows.reduce((sum, row) => sum + row.bytes, 0),
  allGzipBytes: rows.reduce((sum, row) => sum + row.gzipBytes, 0),
  initialRendererModules,
  sceneRendererModules,
  layers,
  deferredScene: scene.fileName,
  sceneNotInitiallyImported: !initial.includes(scene.fileName),
  chunks: rows,
};
await mkdir(dirname(resolve(root, output)), { recursive: true });
await writeFile(resolve(root, output), JSON.stringify(report, null, 2) + "\n");
if (!process.argv.includes("--record-baseline")) {
  assert.deepEqual(
    initialRendererModules,
    [],
    "평면/기본 화면에 3D 렌더러가 다시 포함됨",
  );
  assert(report.sceneNotInitiallyImported, "3D 화면의 지연 로딩 경계 손상");
  assert(sceneRendererModules.length > 0, "3D 화면의 렌더러 누락");
  assert(
    layers.every(
      (layer) => layer.planInitiallyAvailable && layer.sceneDeferred,
    ),
    "평면/3D 레이어의 로딩 분리 손상",
  );
}
console.log(
  JSON.stringify({
    initialJsBytes: report.initialJsBytes,
    initialGzipBytes: report.initialGzipBytes,
    initialRendererModuleCount: initialRendererModules.length,
    sceneNotInitiallyImported: report.sceneNotInitiallyImported,
  }),
);
