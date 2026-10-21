import React from 'react';
import { createRoot } from 'react-dom/client';
import { GamePage } from '../domains/game/view/GamePage';
import { ErrorBoundary } from '../shared/exception/ErrorBoundary';
import { ServerConnectionBoundary } from '../shared/ui/ServerConnectionBoundary';
import '../shared/ui/base.css';
import '../shared/ui/game.css';
import '../domains/game/view/play.css';
import '../shared/ui/game-theme.css';
import '../shared/ui/gameplay-chrome.css';
import '../shared/ui/site.css';
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ServerConnectionBoundary>
        <GamePage />
      </ServerConnectionBoundary>
    </ErrorBoundary>
  </React.StrictMode>
);
