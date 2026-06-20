import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TagsManager } from './TagsManager';

describe('TagsManager', () => {
  it('opens tag links from the tag body and only removes via the x control', () => {
    const onTagsChange = vi.fn();

    render(<TagsManager tags={['phishing']} onTagsChange={onTagsChange} inline />);

    const tagLink = screen.getByRole('link', { name: /phishing/i });
    expect(tagLink).toHaveAttribute('href', '/search?tag=phishing');

    tagLink.addEventListener('click', (event) => event.preventDefault(), { capture: true });
    fireEvent.click(tagLink);
    expect(onTagsChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /remove phishing/i }));
    expect(onTagsChange).toHaveBeenCalledWith([]);
  });
});
