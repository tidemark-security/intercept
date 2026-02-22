import React, { useMemo } from 'react';
import { IconButton } from '@/components/buttons/IconButton';
import { Tooltip } from '@/components/overlays/Tooltip';
import { ToggleGroup } from '@/components/buttons/ToggleGroup';
import { useTheme } from '@/contexts/ThemeContext';
import type { TimelineItem } from '@/types/timeline';
import { getTimelineItemIcon, getTimelineItemLabel } from '@/utils/timelineMapping';

import { ArrowDown, ArrowUp, Calendar, Clock, Layers } from 'lucide-react';
export type SortOption = 'created_at' | 'timestamp';
export type SortDirection = 'asc' | 'desc';

export interface TimelineFilterProps {
  /** All timeline items to derive available filter types from */
  items: TimelineItem[];
  
  /** Currently selected item type filter (undefined = 'all') */
  selectedType?: string;
  
  /** Handler for type filter changes */
  onTypeChange: (type: string | undefined) => void;
  
  /** Current sort field */
  sortBy: SortOption;
  
  /** Current sort direction */
  sortDirection: SortDirection;
  
  /** Handler for sort changes */
  onSortChange: (sortBy: SortOption, direction: SortDirection) => void;
  
  /** Whether to group similar items together */
  groupSimilar?: boolean;
  
  /** Handler for group similar toggle */
  onGroupSimilarChange?: (enabled: boolean) => void;
  
  /** Size variant for buttons (mobile vs desktop) */
  buttonSize?: 'small' | 'medium';
  
  /** Additional className for the container */
  className?: string;

  /** Whether the filter controls are disabled */
  disabled?: boolean;
}

/**
 * TimelineFilter - Provides sort and filter controls for timeline items
 * 
 * Features:
 * - Sort dropdown (created_at, timestamp)
 * - Sort direction toggle (asc/desc)
 * - Group similar items toggle
 * - Dynamic filter toggle group based on actual timeline item types
 * - Shows "All" option plus each unique item type present in timeline
 */
export function TimelineFilter({
  items,
  selectedType,
  onTypeChange,
  sortBy,
  sortDirection,
  onSortChange,
  groupSimilar = true,
  onGroupSimilarChange,
  buttonSize = 'small',
  className,
  disabled = false,
}: TimelineFilterProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  // Derive unique item types from the timeline items
  const availableTypes = useMemo(() => {
    const types = new Set<string>();
    
    const addTypesFromItems = (itemList: TimelineItem[]) => {
      itemList.forEach((item) => {
        if (item.type) {
          types.add(item.type);
        }
        // Recursively check replies
        if (item.replies && Array.isArray(item.replies)) {
          const replies = item.replies as TimelineItem[];
          if (replies.length > 0) {
            addTypesFromItems(replies);
          }
        }
      });
    };
    
    addTypesFromItems(items);
    return Array.from(types).sort();
  }, [items]);

  const handleSortToggle = () => {
    const newSortBy = sortBy === 'created_at' ? 'timestamp' : 'created_at';
    onSortChange(newSortBy, sortDirection);
  };

  const toggleSortDirection = () => {
    onSortChange(sortBy, sortDirection === 'asc' ? 'desc' : 'asc');
  };

  const sortLabel = useMemo(() => {
    return sortBy === 'created_at' ? 'Created At' : 'Timestamp';
  }, [sortBy]);

  const neutralControlVariant = isDarkTheme
    ? 'neutral-secondary'
    : 'neutral-tertiary';

  const groupSimilarVariant = groupSimilar
    ? (isDarkTheme ? 'neutral-primary' : 'neutral-tertiary')
    : (isDarkTheme ? 'neutral-secondary' : 'brand-primary');

  return (
    <Tooltip.Provider>
      <div className={`flex w-full items-center mobile:justify-center gap-2 flex-wrap mobile:border-0 border-t border-solid border-neutral-border pt-2 ${className || ''}`}>
        {/* Sort Field Toggle */}
        <Tooltip.Root>
          <Tooltip.Trigger asChild>
            <IconButton
              disabled={disabled}
              size={buttonSize}
              variant={neutralControlVariant}
              icon={sortBy === 'created_at' ? <Calendar /> : <Clock />}
              onClick={handleSortToggle}
            />
          </Tooltip.Trigger>
          <Tooltip.Content
            side="bottom"
            align="center"
            sideOffset={4}
          >
            Sort by: {sortLabel}
          </Tooltip.Content>
        </Tooltip.Root>

        {/* Sort Direction Toggle */}
        <Tooltip.Root>
          <Tooltip.Trigger asChild>
            <IconButton
              disabled={disabled}
              size={buttonSize}
              variant={neutralControlVariant}
              icon={sortDirection === 'asc' ? <ArrowUp /> : <ArrowDown />}
              onClick={toggleSortDirection}
            />
          </Tooltip.Trigger>
          <Tooltip.Content
            side="bottom"
            align="center"
            sideOffset={4}
          >
            {sortDirection === 'asc' ? 'Oldest First' : 'Newest First'}
          </Tooltip.Content>
        </Tooltip.Root>

        {/* Group Similar Toggle Button */}
        {onGroupSimilarChange && (
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <IconButton
                disabled={disabled}
                size={buttonSize}
                variant={groupSimilarVariant}
                icon={<Layers />}
                onClick={() => onGroupSimilarChange(!groupSimilar)}
              />
            </Tooltip.Trigger>
            <Tooltip.Content
              side="bottom"
              align="center"
              sideOffset={4}
            >
              Group Similar Items
            </Tooltip.Content>
          </Tooltip.Root>
        )}

        {/* Type Filter Toggle Group - Horizontal */}
        <ToggleGroup 
          value={selectedType || 'all'} 
          className="border rounded-md border-neutral-border"
          onValueChange={(value: string) => {
            onTypeChange(value === 'all' ? undefined : value);
          }}
        >
          {/* All option - always present */}
          <ToggleGroup.Item disabled={disabled} icon={null} value="all" className='w-auto'>
            All
          </ToggleGroup.Item>
          
          {/* Dynamic options based on actual timeline items */}
          {availableTypes.map((type) => {
            const Icon = getTimelineItemIcon(type);
            const label = getTimelineItemLabel(type);
            
            return (
              <ToggleGroup.Item 
                disabled={disabled}
                key={type} 
                icon={<Icon />} 
                value={type}
                className='w-auto'
              >
                {label}
              </ToggleGroup.Item>
            );
          })}
        </ToggleGroup>
      </div>
    </Tooltip.Provider>
  );
}

export default TimelineFilter;
