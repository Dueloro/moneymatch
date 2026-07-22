import * as Sentry from '@sentry/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { AuthProvider } from './auth/AuthProvider';
import { Toaster } from './components/ui/Toaster';
import { env } from './lib/env';
import { queryClient } from './lib/queryClient';
import './styles/index.css';

if (env.sentryDsn) {
  Sentry.init({
    dsn: env.sentryDsn,
    dataCollection: {
      // Collect user info (IP, email) and HTTP request bodies.
      // To opt out: set userInfo: false and httpBodies: []
    },
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
          <Toaster />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
