/**
 * InlineMarkdown component for rendering inline-only markdown.
 * 
 * Supports: bold, italic, underline, strikethrough, links, and inline code.
 * Does NOT support block-level elements like headers, lists, blockquotes, or code blocks.
 * 
 * Designed for use in contexts where only inline formatting is appropriate,
 * such as reasoning bullets, descriptions, or labels.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import { LinkBadge } from './LinkBadge';
import { cn } from '@/utils/cn';
import { useTheme } from '@/contexts/ThemeContext';

export interface InlineMarkdownProps {
  /** The markdown content to render */
  content: string;
  /** Additional class names for the wrapper span */
  className?: string;
}

/**
 * Sanitization config for inline-only markdown.
 * Only allows inline formatting tags - no block elements.
 */
const inlineSanitizeConfig = {
  tagNames: [
    'strong',  // **bold**
    'em',      // *italic*
    'u',       // (not standard markdown, but allowed if present)
    's',       // ~~strikethrough~~ (GFM)
    'del',     // ~~strikethrough~~ alternate
    'a',       // [links](url)
    'code',    // `inline code`
  ],
  attributes: {
    a: ['href'],
    '*': ['className'],
  },
  protocols: {
    href: ['http', 'https', 'mailto'],
  },
};

export function InlineMarkdown({ content, className }: InlineMarkdownProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  if (!content || content.trim() === '') {
    return null;
  }

  return (
    <span className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, inlineSanitizeConfig]]}
        components={{
          // Override p to render as fragment - avoids block nesting
          p: ({ children }) => <>{children}</>,
          // Inline formatting with consistent styling
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          u: ({ children }) => <u>{children}</u>,
          s: ({ children }) => <s className="line-through">{children}</s>,
          del: ({ children }) => <del className="line-through">{children}</del>,
          code: ({ children }) => (
            <code
              className={cn(
                'text-brand-300 font-mono px-[6px] py-[2px] rounded text-sm',
                isDarkTheme ? 'bg-neutral-200' : 'bg-neutral-600'
              )}
            >
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <LinkBadge href={href || '#'}>
              {children}
            </LinkBadge>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </span>
  );
}

export default InlineMarkdown;
