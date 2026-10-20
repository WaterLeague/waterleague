(() => {
  const script = document.currentScript;
  performance.setResourceTimingBufferSize(5000);
  const initialCaches = caches.keys();
  const longTasks = [];
  let firstWebglDrawMs = null;
  let firstMapDomMs = null;
  let pendingFetches = 0;
  let fetches = 0;
  let cancelledFetches = 0;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    pendingFetches++;
    fetches++;
    try {
      return await originalFetch(...args);
    } catch (error) {
      if (error?.name === 'AbortError') cancelledFetches++;
      throw error;
    } finally {
      pendingFetches--;
    }
  };
  // 첫 GPU 그리기 시각만 관측하고 원 렌더 인수·결과는 변경하지 않는다.
  for (const Constructor of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!Constructor) continue;
    for (const name of [
      'drawElements',
      'drawArrays',
      'drawElementsInstanced',
      'drawArraysInstanced',
    ]) {
      const original = Constructor.prototype[name];
      if (!original) continue;
      Constructor.prototype[name] = function (...args) {
        firstWebglDrawMs ??= performance.now();
        return original.apply(this, args);
      };
    }
  }
  if (PerformanceObserver.supportedEntryTypes.includes('longtask'))
    new PerformanceObserver((list) => {
      longTasks.push(
        ...list.getEntries().map(({ startTime, duration }) => ({ startTime, duration }))
      );
    }).observe({ type: 'longtask', buffered: true });
  addEventListener('DOMContentLoaded', () => {
    const panel = document.createElement('aside');
    panel.style.cssText =
      'position:fixed;right:8px;top:8px;z-index:1000;background:white;border:2px solid #874;padding:8px;width:350px;font:11px system-ui';
    panel.innerHTML =
      '<strong>로컬 배포 빌드 로딩 계측</strong><p id="native-load-status"></p><button id="native-load-capture">현재 로딩 결과 기록</button><pre id="native-load-result" style="white-space:pre-wrap;max-height:200px;overflow:auto">측정 중</pre>';
    document.body.append(panel);
    const status = panel.querySelector('#native-load-status');
    const output = panel.querySelector('#native-load-result');
    const timer = setInterval(() => {
      const root = document.getElementById('root');
      if (
        firstMapDomMs === null &&
        root?.querySelector('canvas,svg.city-plan') &&
        !root.textContent.includes('서울 3D 지도 구성 중')
      )
        firstMapDomMs = performance.now();
      status.textContent = `첫 WebGL ${firstWebglDrawMs?.toFixed(1) ?? '대기'}ms · 대기 요청 ${pendingFetches}`;
    }, 200);
    panel.querySelector('#native-load-capture').onclick = async () => {
      const resources = performance.getEntriesByType('resource').map((entry) => ({
        path: new URL(entry.name).pathname,
        initiatorType: entry.initiatorType,
        startTime: entry.startTime,
        responseEnd: entry.responseEnd,
        duration: entry.duration,
        transferSize: entry.transferSize,
        encodedBodySize: entry.encodedBodySize,
        decodedBodySize: entry.decodedBodySize,
        responseStatus: entry.responseStatus,
      }));
      const memory = performance.memory;
      const canvas = document.querySelector('canvas');
      output.textContent = JSON.stringify(
        {
          schemaVersion: 1,
          status: firstWebglDrawMs !== null ? 'MEASURED' : 'FIRST_WEBGL_DRAW_NOT_OBSERVED',
          citySha256: script.dataset.citySha256,
          instrumentationSha256: script.dataset.sourceSha256,
          cacheNamesAtStart: await initialCaches,
          firstWebglDrawMs,
          firstMapDomMs,
          capturedAtMs: performance.now(),
          fetches,
          pendingFetches,
          cancelledFetches,
          transferredBytes: resources.reduce((sum, entry) => sum + entry.transferSize, 0),
          resources,
          longTasks,
          approximateChromiumHeap: memory
            ? {
                usedJSHeapSize: memory.usedJSHeapSize,
                totalJSHeapSize: memory.totalJSHeapSize,
                jsHeapSizeLimit: memory.jsHeapSizeLimit,
                scope: 'BROWSER_ESTIMATE_NOT_TOTAL_PROCESS_GPU_OR_WORKERS',
              }
            : null,
          viewport: [innerWidth, innerHeight],
          canvas: canvas ? [canvas.width, canvas.height] : null,
          userAgent: navigator.userAgent,
          productionBundle: true,
          tlsDeploymentMeasured: false,
        },
        null,
        2
      );
      clearInterval(timer);
    };
  });
})();
