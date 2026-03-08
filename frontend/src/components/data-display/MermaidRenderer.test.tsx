import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ThemeProvider } from '@/contexts/ThemeContext';

import MermaidRenderer from './MermaidRenderer';

describe('MermaidRenderer', () => {
  it('shows a streaming placeholder instead of rendering partial Mermaid content', () => {
    render(
      <ThemeProvider>
        <MermaidRenderer code={'graph TD\nA-->B'} isStreaming={true} />
      </ThemeProvider>
    );

    expect(screen.getByTestId('mermaid-streaming-placeholder')).toBeInTheDocument();
    expect(screen.getByText(/AI is sketching the diagram/i)).toBeInTheDocument();
    expect(screen.queryByTestId('mermaid-diagram')).not.toBeInTheDocument();
  });
});