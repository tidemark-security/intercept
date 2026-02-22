/**
 * SearchResultRow - Unified search result row component
 * 
 * Used in both GlobalSearch modal and SearchPage for consistent rendering.
 * Supports optional selection state for keyboard navigation.
 */

import React from 'react';
import { Badge } from '@/components/data-display/Badge';
import { Tag } from '@/components/data-display/Tag';
import { Priority } from '@/components/misc/Priority';
import { State } from '@/components/misc/State';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';

import { CopyableTimestamp } from '@/components/data-display/CopyableTimestamp';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { TimelineItemSnippet, hasDisplayableContent } from '@/components/search/TimelineItemSnippet';
import { SearchHighlight } from '@/components/search/SearchHighlight';
import { User } from 'lucide-react';
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
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  const baseClassName = "group flex w-full cursor-pointer items-start gap-3 rounded-md px-4 py-4 transition-colors";
  const selectedClassName = cn('border border-solid', {
    'bg-neutral-100 border-transparent': isSelected && isDarkTheme,
    'bg-neutral-300 border-transparent': isSelected && !isDarkTheme,
    'border-neutral-border hover:bg-neutral-50': !isSelected && isDarkTheme,
    'border-neutral-border hover:bg-neutral-100 hover:border-neutral-200': !isSelected && !isDarkTheme,
  });
  const visibleTags = item.tags?.slice(0, 3) || [];
  const additionalTagCount = item.tags && item.tags.length > 3 ? item.tags.length - 3 : 0;
  
  return (
    <div
      role={role}
      tabIndex={role === 'button' ? 0 : undefined}
      aria-selected={role === 'option' ? isSelected : undefined}
      className={`${baseClassName} ${selectedClassName}`}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onKeyDown={role === 'button' ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      {icon && (
        <div className="flex-shrink-0">
          {icon}
        </div>
      )}
      <div className="flex min-w-0 grow shrink-0 basis-0 flex-col items-start justify-center gap-1 self-stretch">
        <div className="flex w-full min-w-0 items-start gap-1 pb-1">
          <span
            className={cn(
              'min-w-0 grow shrink basis-0 text-body-bold font-body-bold text-default-font line-clamp-1',
              {
                'group-hover:text-brand-400': isDarkTheme,
                'text-accent-1-400': isSelected && isDarkTheme,
              }
            )}
          >
            {item.title}
          </span>
          <div className="flex max-w-full flex-shrink-0 flex-wrap items-center justify-end gap-2">
            {item.priority && (
              <Priority priority={mapPriority(item.priority)} size="mini" />
            )}
            {item.status && (
              <State state={mapState(item.status, item.entity_type)} variant="mini" />
            )}
            <CopyableTimestamp value={item.created_at} showFull={false} className="hidden md:flex" />
            <Badge className="h-6 flex-none" variant="neutral">
              {item.human_id}
            </Badge>
          </div>
        </div>
        <SmartSnippet snippet={item.snippet} searchQuery={searchQuery} />
        {visibleTags.length > 0 && (
          <div className="flex w-full flex-wrap items-center gap-1 pt-1">
            {visibleTags.map((tag) => (
              <Tag key={tag} tagText={tag} showDelete={false} p="0" />
            ))}
            {additionalTagCount > 0 && (
              <span className="text-caption font-caption text-subtext-color">+{additionalTagCount} more</span>
            )}
          </div>
        )}
        <div className="flex w-full flex-col items-start gap-1 pt-1 sm:flex-row sm:items-center">
          <div className="flex w-full min-w-0 grow shrink basis-0 flex-wrap items-center gap-1 self-stretch">
            <User className="text-body font-body text-default-font h-3 w-3" />
            <span className="line-clamp-1 min-w-0 grow shrink basis-0 text-caption font-caption text-default-font">
              {item.assignee || 'Unassigned'}
            </span>
          </div>
          <div className="flex w-full items-center justify-start gap-1 sm:ml-auto sm:w-auto sm:justify-end">
            <RelativeTime
              value={item.updated_at || item.created_at}
              className="text-caption font-caption text-default-font text-left sm:text-right"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default SearchResultRow;
