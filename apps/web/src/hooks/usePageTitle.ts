import { useEffect } from 'react';

const BASE = 'Money Match';

/**
 * Sets the document title for a route and restores the base title on unmount,
 * so browser tabs, history, and bookmarks read as distinct pages instead of one
 * catch-all SPA title. Pass the page name only; the brand suffix is added here.
 */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${BASE}` : BASE;
    return () => {
      document.title = `${BASE}: put your skill on the line`;
    };
  }, [title]);
}
