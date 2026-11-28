import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CodeBlock, TRUNCATED_LINE_MAX_CHARS, truncateLongLine } from './CodeBlock';

describe('truncateLongLine', () => {
  it('leaves lines within the limit unchanged', () => {
    expect(truncateLongLine('short line')).toBe('short line');
    expect(truncateLongLine('a'.repeat(TRUNCATED_LINE_MAX_CHARS))).toBe('a'.repeat(TRUNCATED_LINE_MAX_CHARS));
  });

  it('cuts longer lines and appends an ellipsis', () => {
    expect(truncateLongLine('a'.repeat(TRUNCATED_LINE_MAX_CHARS + 1))).toBe(`${'a'.repeat(TRUNCATED_LINE_MAX_CHARS)}…`);
  });
});

describe('CodeBlock', () => {
  const longLine = 'x'.repeat(5000);
  const code = `first\n${longLine}\nthird\nfourth`;

  it('truncates long lines onto one row when truncateLongLines is set', () => {
    const { container } = render(
      <CodeBlock language="text" code={code} resolvedTheme="dark" maxLines={3} truncateLongLines />,
    );

    const text = container.querySelector('code')?.textContent ?? '';
    expect(text).toContain(`${'x'.repeat(TRUNCATED_LINE_MAX_CHARS)}…`);
    expect(text).not.toContain('x'.repeat(TRUNCATED_LINE_MAX_CHARS + 1));
    expect(text).not.toContain('fourth');
    expect(container.querySelector('code')?.getAttribute('style')).toContain('white-space: pre;');
  });

  it('keeps full lines and wrapping by default', () => {
    const { container } = render(<CodeBlock language="text" code={code} resolvedTheme="dark" />);

    const codeEl = container.querySelector('code');
    expect(codeEl?.textContent).toContain(longLine);
    expect(codeEl?.getAttribute('style')).toContain('white-space: pre-wrap;');
  });
});
