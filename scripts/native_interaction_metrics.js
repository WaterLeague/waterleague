(() => {
  // 계측 참조를 유지하므로 이 기록만으로 GC·전체 GPU 메모리 누수를 판정하지 않는다.
  const contexts = new Map();
  let drawsSinceFrame = 0;
  let recording = null;
  let serial = 0;
  const samples = [];
  const markDraw = () => {
    drawsSinceFrame++;
  };
  for (const Constructor of [
    window.WebGLRenderingContext,
    window.WebGL2RenderingContext,
  ]) {
    if (!Constructor) continue;
    for (const method of [
      "drawElements",
      "drawArrays",
      "drawElementsInstanced",
      "drawArraysInstanced",
    ]) {
      const original = Constructor.prototype[method];
      if (!original) continue;
      Constructor.prototype[method] = function (...args) {
        markDraw();
        return original.apply(this, args);
      };
    }
    for (const kind of [
      "Buffer",
      "Texture",
      "Program",
      "Framebuffer",
      "Renderbuffer",
    ]) {
      for (const operation of ["create", "delete"]) {
        const original = Constructor.prototype[operation + kind];
        Constructor.prototype[operation + kind] = function (...args) {
          const result = original.apply(this, args);
          let state = contexts.get(this);
          if (!state) {
            state = {};
            contexts.set(this, state);
          }
          state[kind] ??= new Set();
          if (operation === "create" && result) state[kind].add(result);
          if (operation === "delete") state[kind].delete(args[0]);
          return result;
        };
      }
    }
  }
  const resources = () =>
    [...contexts].map(([context, state]) => ({
      lost: context.isContextLost(),
      objects: Object.fromEntries(
        Object.entries(state).map(([k, v]) => [k, v.size]),
      ),
    }));
  const memory = () =>
    performance.memory
      ? {
          usedJSHeapSize: performance.memory.usedJSHeapSize,
          totalJSHeapSize: performance.memory.totalJSHeapSize,
        }
      : null;
  let previous = null;
  const tick = (time) => {
    if (recording && previous !== null) {
      const gap = time - previous;
      recording.intervals.push(gap);
      recording.callbackFrames++;
      // 같은 애니메이션 콜백 구간의 여러 그리기 호출은 한 프레임으로 센다.
      if (drawsSinceFrame > 0) recording.drawFrames++;
      recording.drawCalls += drawsSinceFrame;
      if (time - recording.lastMemoryAt >= 5000) {
        recording.memory.push({
          atMs: time - recording.startedAt,
          ...memory(),
        });
        recording.lastMemoryAt = time;
      }
    }
    previous = time;
    drawsSinceFrame = 0;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  addEventListener("DOMContentLoaded", () => {
    const panel = document.getElementById("native-load-panel");
    const row = document.createElement("div");
    row.innerHTML =
      '<label>측정 구간 <input id="interaction-label" value="overview" style="width:110px"></label> <button id="interaction-start">구간 측정 시작</button> <button id="interaction-stop">구간 측정 종료</button><pre id="interaction-result" style="white-space:pre-wrap;max-height:130px;overflow:auto">대기</pre>';
    panel.append(row);
    const output = row.querySelector("#interaction-result");
    row.querySelector("#interaction-start").onclick = () => {
      if (recording) return;
      const now = performance.now();
      recording = {
        sequence: ++serial,
        label: row.querySelector("input").value,
        startedAt: now,
        lastMemoryAt: now,
        intervals: [],
        callbackFrames: 0,
        drawFrames: 0,
        drawCalls: 0,
        memory: [{ atMs: 0, ...memory() }],
        gpuObjectsAtStart: resources(),
        visibilityAtStart: document.visibilityState,
      };
      previous = null;
      drawsSinceFrame = 0;
      output.textContent = "측정 중";
    };
    row.querySelector("#interaction-stop").onclick = () => {
      if (!recording) return;
      const time = performance.now(),
        r = recording;
      recording = null;
      const sorted = [...r.intervals].sort((a, b) => a - b),
        percentile = (q) =>
          sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))] ??
          null;
      const durationMs = time - r.startedAt;
      samples.push({
        sequence: r.sequence,
        label: r.label,
        durationMs,
        callbackFrames: r.callbackFrames,
        drawFrames: r.drawFrames,
        drawCalls: r.drawCalls,
        callbackFps: (r.callbackFrames * 1000) / durationMs,
        observedDrawFps: (r.drawFrames * 1000) / durationMs,
        intervalMs: {
          p50: percentile(0.5),
          p95: percentile(0.95),
          p99: percentile(0.99),
          max: sorted.at(-1) ?? null,
          over50: sorted.filter((x) => x > 50).length,
          over100: sorted.filter((x) => x > 100).length,
        },
        memory: [...r.memory, { atMs: durationMs, ...memory() }],
        gpuObjectsAtStart: r.gpuObjectsAtStart,
        gpuObjectsAtEnd: resources(),
        visibilityAtStart: r.visibilityAtStart,
        visibilityAtEnd: document.visibilityState,
      });
      output.textContent = JSON.stringify({
        schemaVersion: 1,
        scope:
          "INSTRUMENTED_BROWSER_CALLBACK_AND_WEBGL_DRAW_FRAMES_NOT_GPU_PRESENT_TIME",
        heapScope: "CHROMIUM_ESTIMATE_NOT_TOTAL_PROCESS_GPU_OR_WORKERS",
        samples,
      });
    };
  });
})();
