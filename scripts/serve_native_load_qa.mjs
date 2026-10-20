import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, symlink, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "../frontend/node_modules/vite/dist/node/index.js";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const frontend = path.join(root, "frontend");
const directory = path.join(root, "tmp/native-load-qa-" + Date.now());
const hash = (raw) => createHash("sha256").update(raw).digest("hex");
const html = await readFile(path.join(frontend, "dist/index.html"), "utf8");
const instrumentation = await readFile(
  path.join(frontend, "qa/nativeLoadMetrics.js"),
);
const city = await readFile(
  path.join(frontend, "dist/data/seoul-native-v1/city.json"),
);
const citySha = hash(city);
assert.equal(
  citySha,
  "67a8b80b7036590973b7db99053521333f9405e1076a7939bfe491c43296dd6c",
);
await mkdir(directory);
for (const name of ["assets", "data", "fonts"])
  await symlink(path.join(frontend, "dist", name), path.join(directory, name));
await writeFile(
  path.join(directory, "native-load-metrics.js"),
  instrumentation,
  { flag: "wx" },
);
await writeFile(
  path.join(directory, "index.html"),
  html.replace(
    "<head>",
    `<head><script src="/native-load-metrics.js" data-city-sha256="${citySha}" data-source-sha256="${hash(instrumentation)}"></script>`,
  ),
  { flag: "wx" },
);
const reservation = createServer();
await new Promise((resolve, reject) => {
  reservation.once("error", reject);
  reservation.listen(0, "127.0.0.1", resolve);
});
const port = reservation.address().port;
await new Promise((resolve) => reservation.close(resolve));
const server = await preview({
  configFile: false,
  root: frontend,
  build: { outDir: directory },
  preview: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
});
process.on("SIGTERM", async () => {
  await server.close();
  process.exit(0);
});
process.on("SIGINT", async () => {
  await server.close();
  process.exit(0);
});
console.log(
  JSON.stringify({
    url: `http://127.0.0.1:${port}/`,
    directory: path.relative(root, directory),
    citySha256: citySha,
    instrumentationSha256: hash(instrumentation),
  }),
);
