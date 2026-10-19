import React from 'react';
import { createRoot } from 'react-dom/client';
import { GamePage } from '../domains/game/view/GamePage';
import { ErrorBoundary } from '../shared/exception/ErrorBoundary';
import '../shared/ui/base.css';
import '../shared/ui/game.css';
import '../domains/game/view/play.css';
import '../shared/ui/game-theme.css';
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <GamePage />
    </ErrorBoundary>
  </React.StrictMode>
);
