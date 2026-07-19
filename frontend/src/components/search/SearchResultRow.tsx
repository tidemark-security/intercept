/**
 * SearchResultRow - Unified search result row component
 * 
 * Used in both GlobalSearch modal and SearchPage for consistent rendering.
 * Supports optional selection state for keyboard navigation.
 */

import React from 'react';

import { CopyableTimestamp } from '@/components/data-display/CopyableTimestamp';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { MenuCard } from '@/components/cards/MenuCard';
import { TimelineItemSnippet, hasDisplayableContent } from '@/components/search/TimelineItemSnippet';
import { SearchHighlight } from '@/components/search/SearchHighlight';
import { 
  ExtendedSearchResultItem, 
  mapPriority, 
  mapState, 
  tryParseTimelineItemJson 
} from './searchUtils';

interface SearchResultRowProps {
  /** Search result item data */
  item: ExtendedSearchResultItem;
  /** Click handler for navigation */
  onClick: () => void;
  /** Search query for highlighting matches */
  searchQuery?: string;
  /** Active tag filters used for tag chip highlighting */
  selectedTags?: string[];
  /** Whether this row is currently selected (for keyboard navigation) */
  isSelected?: boolean;
  /** Mouse enter handler (for keyboard navigation) */
  onMouseEnter?: () => void;
  /** Optional icon to show before the result */
  icon?: React.ReactNode;
  /** ARIA role for accessibility */
  role?: 'button' | 'option';
}

function getTimelineTagMatches(item: ExtendedSearchResultItem) {
  const seen = new Set<string>();
  return (item.tag_matches || []).filter((match) => {
    if (match.source !== 'timeline') return false;
    const key = `${String(match.tag || '').toLowerCase()}|${String(match.filter || '').toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function getTimelineSnippetTags(item: ExtendedSearchResultItem) {
  const timelineItem = tryParseTimelineItemJson(item.snippet || '');
  const tags = timelineItem?.tags;
  if (!Array.isArray(tags)) return [];

  return tags.filter((tag): tag is string => typeof tag === 'string' && tag.trim().length > 0);
}

function getSearchResultTags(item: ExtendedSearchResultItem) {
  const timelineTags = new Set<string>();
  const childTags = [
    ...getTimelineTagMatches(item).map((match) => match.tag),
    ...getTimelineSnippetTags(item),
  ].filter((tag) => {
    const key = tag.toLowerCase();
    if (timelineTags.has(key)) return false;
    timelineTags.add(key);
    return true;
  });

  return [
    ...(item.tags || []),
    ...childTags.map((tag) => ({
      tag,
      source: 'timeline' as const,
    })),
  ];
}

function getTagHighlightTerms(searchQuery?: string, selectedTags: string[] = []) {
  const terms = new Set<string>();

  selectedTags.forEach((tag) => {
    const value = tag.trim();
    if (value) terms.add(value);
  });

  const query = searchQuery?.trim();
  if (!query || query === "*") return Array.from(terms);

  terms.add(query);
  query
    .split(/\s+/)
    .map((term) => term.replace(/^[`"'([{<]+|[`"')\]}>.,:;!?]+$/g, "").trim())
    .filter((term) => term && term !== "*")
    .forEach((term) => terms.add(term));

  return Array.from(terms);
}

/**
 * Render snippet - either as a timeline item card or highlighted text.
 * Falls back to highlighted text if timeline item has no displayable content.
 */
function SmartSnippet({ snippet, searchQuery }: { snippet: string; searchQuery?: string }) {
  const timelineItem = tryParseTimelineItemJson(snippet);
  
  // Only render as a timeline card if the item has meaningful content
  // Entity reference types (alert, case, task) and empty items fall through to text
  if (timelineItem && hasDisplayableContent(timelineItem)) {
    return (
      <TimelineItemSnippet 
        item={timelineItem}
        highlightQuery={searchQuery}
      />
    );
  }
  
  // If we parsed JSON but it wasn't displayable (entity reference), don't show raw JSON
  // The entity title is already shown in the search result header
  if (timelineItem) {
    return null;
  }
  
  return <HighlightedSnippet snippet={snippet} />;
}

/**
 * Render snippet with highlighted matches
 */
function HighlightedSnippet({ snippet }: { snippet: string }) {
  const parts = snippet.split(/(<mark>.*?<\/mark>)/g);
  
  return (
    <span className="line-clamp-2 text-caption font-caption text-subtext-color break-words">
      {parts.map((part, i) => {
        if (part.startsWith('<mark>')) {
          const content = part.replace(/<\/?mark>/g, '');
          return <SearchHighlight key={i}>{content}</SearchHighlight>;
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

export function SearchResultRow({
  item,
  onClick,
  searchQuery,
  selectedTags = [],
  isSelected = false,
  onMouseEnter,
  icon,
  role = 'button',
}: SearchResultRowProps) {
  const variant = isSelected ? 'selected' : 'default';
  const tags = getSearchResultTags(item);
  const highlightedTags = getTagHighlightTerms(searchQuery, selectedTags);
  
  return (
    <MenuCard
      id={item.human_id}
      title={item.title}
      timestamp={
        <CopyableTimestamp
          value={item.created_at}
          showFull={false}
        />
      }
      assignee={item.assignee || 'Unassigned'}
      tags={tags}
      highlightedTags={highlightedTags}
      state={item.status ? mapState(item.status, item.entity_type) : undefined}
      priority={item.priority ? mapPriority(item.priority) : undefined}
      variant={variant}
      leadingContent={icon}
      bodyContent={
        <>
          <SmartSnippet snippet={item.snippet} searchQuery={searchQuery} />
          <RelativeTime
            value={item.updated_at || item.created_at}
            className="text-caption font-caption text-subtext-color"
          />
        </>
      }
      role={role}
      tabIndex={role === 'button' ? 0 : undefined}
      aria-selected={role === 'option' ? isSelected : undefined}
      className="group w-full cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-primary"
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onKeyDown={role === 'button' ? (e) => e.key === 'Enter' && onClick() : undefined}
    />
  );
}

export default SearchResultRow;
