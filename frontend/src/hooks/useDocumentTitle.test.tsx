import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { APP_TITLE, formatDocumentTitle, formatEntityTitle, useDocumentTitle } from './useDocumentTitle';

describe('formatDocumentTitle', () => {
  it('suffixes the page label with the app name', () => {
    expect(formatDocumentTitle('Alerts')).toBe('Alerts - Tidemark Intercept');
  });

  it('falls back to the app name without a label', () => {
    expect(formatDocumentTitle()).toBe(APP_TITLE);
    expect(formatDocumentTitle('  ')).toBe(APP_TITLE);
  });
});

describe('formatEntityTitle', () => {
  it('joins the human ID and title', () => {
    expect(formatEntityTitle('CAS-0015301', 'Attachment testing')).toBe('CAS-0015301: Attachment testing');
  });

  it('uses whichever part is available', () => {
    expect(formatEntityTitle('CAS-0015301', undefined)).toBe('CAS-0015301');
    expect(formatEntityTitle(null, 'Attachment testing')).toBe('Attachment testing');
    expect(formatEntityTitle(null, null)).toBe('');
  });
});

describe('useDocumentTitle', () => {
  afterEach(() => {
    document.title = APP_TITLE;
  });

  it('sets, updates and resets the document title', () => {
    const { rerender, unmount } = renderHook(({ page }) => useDocumentTitle(page), {
      initialProps: { page: 'CAS-0015301' as string | null },
    });
    expect(document.title).toBe('CAS-0015301 - Tidemark Intercept');

    rerender({ page: formatEntityTitle('CAS-0015301', 'Attachment testing') });
    expect(document.title).toBe('CAS-0015301: Attachment testing - Tidemark Intercept');

    unmount();
    expect(document.title).toBe(APP_TITLE);
  });
});
