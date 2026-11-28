import { useEffect } from 'react';

export const APP_TITLE = 'Tidemark Intercept';

/** "<page> - Tidemark Intercept", or just the app name when there is no page label. */
export function formatDocumentTitle(page?: string | null): string {
  const label = page?.trim();
  return label ? `${label} - ${APP_TITLE}` : APP_TITLE;
}

/** "<HUMAN-ID>: <title>", falling back to whichever part is available. */
export function formatEntityTitle(humanId?: string | null, title?: string | null): string {
  const id = humanId?.trim();
  const name = title?.trim();
  if (id && name) return `${id}: ${name}`;
  return id || name || '';
}

/** Set the browser tab title for the current page, resetting to the app name on unmount. */
export function useDocumentTitle(page?: string | null): void {
  const title = formatDocumentTitle(page);

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    return () => {
      document.title = APP_TITLE;
    };
  }, []);
}
