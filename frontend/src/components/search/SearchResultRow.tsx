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
  /** Whether this row is currently selected (for keyboard navigation) */
  isSelected?: boolean;
  /** Mouse enter handler (for keyboard navigation) */
  onMouseEnter?: () => void;
  /** Optional icon to show before the result */
  icon?: React.ReactNode;
  /** ARIA role for accessibility */
  role?: 'button' | 'option';
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
  isSelected = false,
  onMouseEnter,
  icon,
  role = 'button',
}: SearchResultRowProps) {
  const variant = isSelected ? 'selected' : 'default';
  
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
      tags={item.tags || []}
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
