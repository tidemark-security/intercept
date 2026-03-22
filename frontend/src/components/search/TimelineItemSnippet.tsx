/**
 * TimelineItemSnippet - Timeline item display for search results
 * 
 * Renders a BaseCard representation of a timeline item when search results
 * match content within timeline items (which come back as JSON snippets).
 * 
 * Uses the standard TimelineCardFactory to generate card props, ensuring
 * consistent rendering with timeline items elsewhere in the app.
 * 
 * Supports text highlighting for search matches by pre-processing item
 * fields to wrap matches with <mark> tags before rendering.
 * 
 * @example
 * ```tsx
 * <TimelineItemSnippet 
 *   item={parsedTimelineItem} 
 *   highlightQuery="malware"
 * />
 * ```
 */

/* eslint-disable react-refresh/only-export-components */

import React from 'react';
import { BaseCard } from '@/components/cards/BaseCard';
import { createTimelineCard, type CardConfig } from '@/components/timeline/TimelineCardFactory';
import { SearchHighlight } from '@/components/search/SearchHighlight';
import type { TimelineItem } from '@/types/timeline';

interface TimelineItemSnippetProps {
  /** Parsed timeline item data */
  item: Partial<TimelineItem> & { type?: string };
  /** Search query to highlight in the card content */
  highlightQuery?: string;
}

/**
 * Apply highlighting to a string by wrapping matches with <mark> tags
 */
function highlightString(text: string, query: string): string {
  if (!query || !text) return text;
  
  // Escape regex special characters
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // Case-insensitive replacement, preserving original case
  return text.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>');
}

/**
 * Recursively apply highlighting to all string fields in an object
 */
function highlightItemFields<T extends Record<string, any>>(item: T, query: string): T {
  if (!query) return item;
  
  const result: Record<string, any> = {};
  
  for (const [key, value] of Object.entries(item)) {
    if (typeof value === 'string') {
      result[key] = highlightString(value, query);
    } else if (Array.isArray(value)) {
      result[key] = value.map(v => 
        typeof v === 'string' ? highlightString(v, query) : v
      );
    } else if (value && typeof value === 'object') {
      result[key] = highlightItemFields(value, query);
    } else {
      result[key] = value;
    }
  }
  
  return result as T;
}

/**
 * Render a React node that may contain <mark> tags for highlighting
 */
function HighlightedNode({ content }: { content: React.ReactNode }) {
  if (typeof content !== 'string') {
    return <>{content}</>;
  }
  
  // Check if content has <mark> tags
  if (!content.includes('<mark>')) {
    return <>{content}</>;
  }
  
  // Convert <mark> tags to styled spans
  const parts = content.split(/(<mark>.*?<\/mark>)/g);
  
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('<mark>')) {
          const text = part.replace(/<\/?mark>/g, '');
          return (
            <SearchHighlight key={i}>
              {text}
            </SearchHighlight>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

/**
 * Process card config to render highlighted strings
 */
function applyHighlightingToCardConfig(config: CardConfig): CardConfig {
  const processNode = (node: React.ReactNode): React.ReactNode => {
    if (typeof node === 'string' && node.includes('<mark>')) {
      return <HighlightedNode content={node} />;
    }
    return node;
  };
  
  return {
    ...config,
    title: processNode(config.title),
    line1: processNode(config.line1),
    line2: processNode(config.line2),
    line3: processNode(config.line3),
    line4: processNode(config.line4),
    accentText: processNode(config.accentText),
  };
}

/**
 * Check if a timeline item has enough content to display meaningfully.
 * Returns false if the item would result in an empty/useless card.
 * 
 * Note: alert, case, and task types are entity references with special handling
 * in TimelineCardFactory that doesn't render useful content in search context.
 */
export function hasDisplayableContent(item: Partial<TimelineItem> & { type?: string }): boolean {
  // Entity reference types don't render meaningful content as cards
  const entityReferenceTypes = ['alert', 'case', 'task'];
  if (item.type && entityReferenceTypes.includes(item.type)) {
    return false;
  }
  
  // Check for any field that would provide meaningful display content
  const contentFields = [
    'description',
    'title',
    'name',
    'process_name',
    'command_line',
    'destination_ip',
    'source_ip',
    'observable_value',
    'observable_type',
    'hostname',
    'mitre_id',
    'file_name',
    'url',
    'subject',
    'registry_key',
    'hash',
    'content',
    'message',
    'from',
    'to',
  ];
  
  const itemAny = item as Record<string, unknown>;
  
  for (const field of contentFields) {
    const value = itemAny[field];
    if (value && typeof value === 'string' && value.trim().length > 0) {
      return true;
    }
  }
  
  return false;
}

export function TimelineItemSnippet({ item, highlightQuery }: TimelineItemSnippetProps) {
  // Check if the item has meaningful content to display
  // If not, return null so the caller can fall back to text display
  if (!hasDisplayableContent(item)) {
    return null;
  }
  
  // Pre-process item to add highlight markers to string fields
  const highlightedItem = highlightQuery 
    ? highlightItemFields(item, highlightQuery)
    : item;
  
  // Use the standard card factory to generate props
  const cardConfig = createTimelineCard(highlightedItem as TimelineItem, {
    size: 'medium',
  });
  
  // Post-process to convert <mark> strings to React elements
  const processedConfig = highlightQuery 
    ? applyHighlightingToCardConfig(cardConfig)
    : cardConfig;

  return (
    <BaseCard
      {...processedConfig}
      size="medium"
      className="w-full max-w-none"
    />
  );
}

export default TimelineItemSnippet;
