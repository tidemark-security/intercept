import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TimelineDescriptionBlock } from './TimelineDescriptionBlock';

describe('TimelineDescriptionBlock', () => {
  it('adds a divider before action buttons when description content exists', () => {
    render(
      <TimelineDescriptionBlock actionButtons={<button type="button">Open link</button>}>
        <p>Description</p>
      </TimelineDescriptionBlock>
    );

    const buttonWrapper = screen.getByRole('button', { name: 'Open link' }).parentElement;

    expect(buttonWrapper).not.toBeNull();
    expect(buttonWrapper?.className).toContain('border-t');
    expect(buttonWrapper?.className).toContain('pt-3');
  });

  it('does not add a divider when only action buttons are present', () => {
    render(
      <TimelineDescriptionBlock actionButtons={<button type="button">Open link</button>}>
        {null}
      </TimelineDescriptionBlock>
    );

    const buttonWrapper = screen.getByRole('button', { name: 'Open link' }).parentElement;

    expect(buttonWrapper).not.toBeNull();
    expect(buttonWrapper?.className).not.toContain('border-t');
    expect(buttonWrapper?.className).not.toContain('pt-3');
  });
});