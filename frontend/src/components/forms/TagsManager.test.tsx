import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OPEN_GLOBAL_SEARCH_EVENT, type OpenGlobalSearchDetail } from '@/components/search/globalSearchEvents';
import { TagsManager } from './TagsManager';

describe('TagsManager', () => {
  it('opens modal search from plain tag body clicks and only removes via the x control', () => {
    const onTagsChange = vi.fn();
    const onOpenSearch = vi.fn<(event: CustomEvent<OpenGlobalSearchDetail>) => void>();
    const handleOpenSearch = (event: Event) => {
      onOpenSearch(event as CustomEvent<OpenGlobalSearchDetail>);
    };
    window.addEventListener(OPEN_GLOBAL_SEARCH_EVENT, handleOpenSearch);

    render(<TagsManager tags={['phishing']} onTagsChange={onTagsChange} inline />);

    const tagLink = screen.getByRole('link', { name: /phishing/i });
    expect(tagLink).toHaveAttribute('href', '/search?tag=phishing');

    fireEvent.click(tagLink);
    expect(onOpenSearch).toHaveBeenCalledTimes(1);
    expect(onOpenSearch.mock.calls[0][0].detail).toEqual({ query: '', tags: ['phishing'] });
    expect(onTagsChange).not.toHaveBeenCalled();

    fireEvent(tagLink, new MouseEvent('auxclick', { bubbles: true, button: 1 }));
    expect(tagLink).toHaveAttribute('href', '/search?tag=phishing');
    expect(onOpenSearch).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /remove phishing/i }));
    expect(onTagsChange).toHaveBeenCalledWith([]);
    expect(onOpenSearch).toHaveBeenCalledTimes(1);

    window.removeEventListener(OPEN_GLOBAL_SEARCH_EVENT, handleOpenSearch);
  });
});
