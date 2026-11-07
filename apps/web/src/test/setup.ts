import '@testing-library/jest-dom/vitest';

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
