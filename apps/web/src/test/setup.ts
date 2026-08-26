import '@testing-library/jest-dom/vitest';

// jsdom lacks matchMedia; some libs probe it. Provide a no-op.
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

// jsdom models focus but has no window manager, so `document.hasFocus()` is
// false until something is focused — a state no real browser tab sits in while
// a user is reading it. Tests that care about focus override this per-case.
if (!document.hasFocus()) {
  Object.defineProperty(document, 'hasFocus', {
    configurable: true,
    writable: true,
    value: () => true,
  });
}
