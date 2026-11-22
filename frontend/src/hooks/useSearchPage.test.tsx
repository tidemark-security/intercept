import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useSearchPage } from './useSearchPage';
import { SearchService } from '@/types/generated/services/SearchService';

describe('useSearchPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it.each([
    { url: '/search?tag=phishing&all_time=true', allTime: true, startDate: null, endDate: null },
    {
      url: '/search?tag=phishing&start=2026-06-01&end=2026-06-20',
      allTime: false,
      startDate: '2026-06-01',
      endDate: '2026-06-20',
    },
  ])('runs filter-only search with the selected date scope ($allTime)', async ({
    url, allTime, startDate, endDate,
  }) => {
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
        <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useSearchPage(), { wrapper });

    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          q: '*',
          tags: ['phishing'],
          allTime,
          startDate,
          endDate,
        }),
      );
    });

    if (!allTime) {
      act(() => result.current.setDateRange({ start: null, end: null }));
      await waitFor(() => {
        expect(searchSpy).toHaveBeenLastCalledWith(expect.objectContaining({
          allTime: true,
          startDate: null,
          endDate: null,
        }));
      });
    }
  });
});
