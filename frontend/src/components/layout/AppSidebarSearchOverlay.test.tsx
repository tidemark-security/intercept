import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OPEN_GLOBAL_SEARCH_EVENT, type OpenGlobalSearchDetail } from '@/components/search/globalSearchEvents';
import { SearchOverlay } from './AppSidebar';

vi.mock('@/components/search/GlobalSearch', () => ({
  GlobalSearch: ({
    open,
    initialTags,
    searchRequestKey,
  }: {
    open: boolean;
    initialTags?: string[];
    searchRequestKey?: number;
  }) =>
    open ? (
      <div data-testid="global-search" data-request-key={searchRequestKey}>
        {initialTags?.join(',')}
      </div>
    ) : null,
}));

describe('SearchOverlay', () => {
  it('opens global search with tags from the open search event', () => {
    render(<SearchOverlay />);

    fireEvent(
      window,
      new CustomEvent<OpenGlobalSearchDetail>(OPEN_GLOBAL_SEARCH_EVENT, {
        detail: { query: '', tags: ['phishing'] },
      }),
    );

    expect(screen.getByTestId('global-search')).toHaveTextContent('phishing');
    expect(screen.getByTestId('global-search')).toHaveAttribute('data-request-key', '1');
  });
});
