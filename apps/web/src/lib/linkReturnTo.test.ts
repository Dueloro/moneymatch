import { beforeEach, describe, expect, it } from 'vitest';

import { peekLinkReturnTo, setLinkReturnTo } from './linkReturnTo';

describe('peekLinkReturnTo', () => {
  beforeEach(() => sessionStorage.clear());

  it('keeps same-site paths with their query', () => {
    setLinkReturnTo('/pools?tab=open');
    expect(peekLinkReturnTo()).toBe('/pools?tab=open');
  });

  it.each([
    '//evil.example',
    '/\\evil.example',
    '\\\\evil.example',
    'https://evil.example',
    'javascript:alert(1)',
    '',
  ])('falls back to /play for %j', (value) => {
    setLinkReturnTo(value);
    expect(peekLinkReturnTo()).toBe('/play');
  });
});
