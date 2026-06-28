import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useSearchPage } from './useSearchPage';
import { SearchService } from '@/types/generated/services/SearchService';

describe('useSearchPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('runs filter-only search when URL contains only tag filters', async () => {
    const searchSpy = vi.spyOn(SearchService, 'unifiedSearchApiV1SearchGet').mockResolvedValue({
      results: [],
      total: 0,
      skip: 0,
      limit: 20,
      query: '*',
      entity_types: ['alert', 'case', 'task'],
      date_range: {
        start: '2026-06-01T00:00:00Z',
        end: '2026-06-20T00:00:00Z',
      },
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/search?tag=phishing']}>{children}</MemoryRouter>
      </QueryClientProvider>
    );

    renderHook(() => useSearchPage(), { wrapper });

    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          q: '*',
          tags: ['phishing'],
        }),
      );
    });
  });
});
