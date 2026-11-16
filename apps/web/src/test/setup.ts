import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// Server config is fixed for every test; a test that needs another value re-mocks it.
vi.mock('../hooks/useConfig', () => {
  const data = {
    excluded_states: ['AZ', 'FL'],
    rake_bps: 1000,
    deposit_presets_cents: [1000, 2500, 5000, 10000],
  };
  return {
    useConfig: () => ({ data }),
    useIsExcludedState: (code?: string | null) =>
      !!code && data.excluded_states.includes(code),
  };
});

if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}

if (!document.hasFocus()) {
  Object.defineProperty(document, 'hasFocus', {
    configurable: true,
    writable: true,
    value: () => true,
  });
}
