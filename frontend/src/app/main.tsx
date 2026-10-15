import React from 'react';
import { createRoot } from 'react-dom/client';
import { ExplorerPage } from '../domains/catalog/view/ExplorerPage';
import { ErrorBoundary } from '../shared/exception/ErrorBoundary';
import '../shared/ui/styles.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><ExplorerPage/></ErrorBoundary></React.StrictMode>);
