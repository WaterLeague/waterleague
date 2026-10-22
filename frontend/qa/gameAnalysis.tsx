import { createRoot } from 'react-dom/client';
import { GameAnalysisPanel } from '../src/domains/gameanalysis/view/GameAnalysisPanel';
import '../src/shared/ui/base.css';
import '../src/shared/ui/site.css';
import '../src/domains/competition/view/competition.css';
if (!import.meta.env.DEV || !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
  throw new Error('로컬 검토 전용');
const originalFetch = window.fetch.bind(window);
const saved = await originalFetch('/qa/game-analysis-preview.local.json').then((r) => r.json());
window.fetch = async (input, options) => {
  const path =
    typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
  if (path === '/api/v1/qa/game-analysis')
    return new Response(JSON.stringify(saved.analysis), {
      headers: { 'Content-Type': 'application/json' },
    });
  if (path === '/api/v1/qa/game-analysis/summary' && options?.method === 'POST')
    return new Response(JSON.stringify(saved.summary), {
      headers: { 'Content-Type': 'application/json' },
    });
  return originalFetch(input, options);
};
createRoot(document.getElementById('root')!).render(
  <div className="game-shell">
    <main className="site-page contests-page">
      <p style={{ color: '#62758b', fontSize: 12 }}>
        로컬 검토 · 운영 익명 집계와 실제 Upstage 응답의 저장본 · 추가 AI 호출 없음
      </p>
      <h1>게임 분석</h1>
      <GameAnalysisPanel endpoint="/qa/game-analysis" />
    </main>
  </div>
);
