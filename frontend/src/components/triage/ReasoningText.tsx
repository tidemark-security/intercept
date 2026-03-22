/**
 * ReasoningText component for rendering AI reasoning bullets with inline markdown.
 * 
 * Supports inline markdown formatting: bold, italic, underline, strikethrough,
 * links, and inline code. Block-level markdown elements are not supported.
 */

import React from 'react';
import { InlineMarkdown } from '@/components/data-display/InlineMarkdown';

export interface ReasoningTextProps {
  /** The reasoning text */
  text: string;
  /** Additional class names for the container span */
  className?: string;
}

export function ReasoningText({ text, className }: ReasoningTextProps) {
  return <InlineMarkdown content={text} className={className} />;
}
