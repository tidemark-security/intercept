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

  it('renders read-only tags between description and action buttons', () => {
    render(
      <TimelineDescriptionBlock actionButtons={<button type="button">Open link</button>} tags={['urgent', 'phishing']}>
        <p>Description</p>
      </TimelineDescriptionBlock>
    );

    const description = screen.getByText('Description');
    const tagRow = screen.getByLabelText('Tags');
    const tag = screen.getByText('urgent');
    const button = screen.getByRole('button', { name: 'Open link' });

    expect(tagRow).toBeInTheDocument();
    expect(tagRow.className).not.toContain('border-t');
    expect(tagRow.className).not.toContain('pt-3');
    expect(screen.getByText('phishing')).toBeInTheDocument();
    expect(description.compareDocumentPosition(tag) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(tag.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps the divider before action buttons when tags are present', () => {
    render(
      <TimelineDescriptionBlock actionButtons={<button type="button">Open link</button>} tags={['urgent']}>
        <p>Description</p>
      </TimelineDescriptionBlock>
    );

    const buttonWrapper = screen.getByRole('button', { name: 'Open link' }).parentElement;

    expect(buttonWrapper).not.toBeNull();
    expect(buttonWrapper?.className).toContain('border-t');
    expect(buttonWrapper?.className).toContain('pt-3');
  });

  it('does not render the tag row without tags', () => {
    render(
      <TimelineDescriptionBlock actionButtons={<button type="button">Open link</button>} tags={[]}>
        <p>Description</p>
      </TimelineDescriptionBlock>
    );

    expect(screen.queryByLabelText('Tags')).not.toBeInTheDocument();
  });
});