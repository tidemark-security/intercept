import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MarkdownContent from './MarkdownContent';
import { ThemeProvider } from '@/contexts/ThemeContext';

vi.mock('@/components/data-display/MermaidRenderer', () => ({
  default: ({ code }: { code: string }) => <div data-testid="mermaid-renderer">{code}</div>,
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
});
