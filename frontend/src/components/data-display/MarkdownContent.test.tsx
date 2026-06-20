import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MarkdownContent from './MarkdownContent';
import { ThemeProvider } from '@/contexts/ThemeContext';

vi.mock('@/components/data-display/MermaidRenderer', () => ({
  default: ({ code, isStreaming }: { code: string; isStreaming?: boolean }) => (
    <div data-testid="mermaid-renderer" data-streaming={isStreaming ? 'true' : 'false'}>
      {code}
    </div>
  ),
}));

describe('MarkdownContent', () => {
  it('renders mermaid fenced code blocks with MermaidRenderer', () => {
    const markdown = '```mermaid\ngraph TD\nA-->B\n```';

    render(
      <ThemeProvider>
        <MarkdownContent content={markdown} />
      </ThemeProvider>
    );

    expect(screen.getByTestId('mermaid-renderer')).toHaveTextContent(/graph TD\s*A-->B/);
    expect(screen.getByTestId('mermaid-renderer')).toHaveAttribute('data-streaming', 'false');
  });

  it('passes the AI streaming flag through to MermaidRenderer', () => {
    const markdown = '```mermaid\ngraph TD\nA-->B\n```';

    render(
      <ThemeProvider>
        <MarkdownContent content={markdown} isStreamingFromAi={true} />
      </ThemeProvider>
    );

    expect(screen.getByTestId('mermaid-renderer')).toHaveAttribute('data-streaming', 'true');
  });

  it('renders non-mermaid code blocks as regular code', () => {
    const markdown = '```ts\nconst value = 1;\n```';

    const { container } = render(
      <ThemeProvider>
        <MarkdownContent content={markdown} />
      </ThemeProvider>
    );

    expect(screen.queryByTestId('mermaid-renderer')).not.toBeInTheDocument();

    const codeElement = container.querySelector('pre code');
    expect(codeElement).not.toBeNull();
    expect(codeElement?.textContent?.replace(/\s+/g, ' ')).toContain('const value = 1;');
  });

  it('opens external badge links in a new tab', () => {
    render(
      <ThemeProvider>
        <MarkdownContent content="[Flashpoint](https://flashpoint.io/report)" />
      </ThemeProvider>
    );

    const link = screen.getByRole('link', { name: /flashpoint/i });

    expect(link).toHaveAttribute('href', 'https://flashpoint.io/report');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('keeps non-external badge links in the current tab', () => {
    render(
      <ThemeProvider>
        <MarkdownContent content="[Email](mailto:analyst@example.com)" />
      </ThemeProvider>
    );

    const link = screen.getByRole('link', { name: /email/i });

    expect(link).toHaveAttribute('href', 'mailto:analyst@example.com');
    expect(link).not.toHaveAttribute('target');
    expect(link).not.toHaveAttribute('rel');
  });
});
