import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OPEN_GLOBAL_SEARCH_EVENT } from '@/components/search/globalSearchEvents';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { TagsManager } from './TagsManager';

describe('TagsManager', () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([false, true])('only removes tags via the x control when editable (inline=%s)', (inline) => {
    const onTagsChange = vi.fn();
    const dispatchEvent = vi.spyOn(window, 'dispatchEvent');

    render(<TagsManager tags={['phishing']} onTagsChange={onTagsChange} inline={inline} />, {
      wrapper: ThemeProvider,
    });

    fireEvent.click(screen.getByText('phishing'));
    expect(onTagsChange).not.toHaveBeenCalled();
    expect(dispatchEvent).not.toHaveBeenCalledWith(expect.objectContaining({ type: OPEN_GLOBAL_SEARCH_EVENT }));
    expect(screen.queryByRole('link', { name: 'phishing' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove phishing' }));
    expect(onTagsChange).toHaveBeenCalledExactlyOnceWith([]);
    expect(dispatchEvent).not.toHaveBeenCalledWith(expect.objectContaining({ type: OPEN_GLOBAL_SEARCH_EVENT }));
  });

  it('opens universal search from read-only tags and keeps their link destination', () => {
    const onTagsChange = vi.fn();
    const dispatchEvent = vi.spyOn(window, 'dispatchEvent');

    render(<TagsManager tags={['phishing']} onTagsChange={onTagsChange} readonly />);

    const tagLink = screen.getByRole('link', { name: /phishing/i });
    expect(tagLink).toHaveAttribute('href', '/search?tag=phishing');

    fireEvent.click(tagLink);
    expect(dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({
      type: OPEN_GLOBAL_SEARCH_EVENT,
      detail: { query: '', tags: ['phishing'] },
    }));
    expect(onTagsChange).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Remove phishing' })).not.toBeInTheDocument();

    dispatchEvent.mockClear();
    fireEvent(tagLink, new MouseEvent('auxclick', { bubbles: true, button: 1 }));
    expect(dispatchEvent).not.toHaveBeenCalledWith(expect.objectContaining({ type: OPEN_GLOBAL_SEARCH_EVENT }));
  });
});
