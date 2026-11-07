import { useEffect } from 'react';

const BASE = 'Money Match';

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${BASE}` : BASE;
    return () => {
      document.title = `${BASE}: put your skill on the line`;
    };
  }, [title]);
}
