import React from 'react';
import { Bell, List, NotebookPen } from 'lucide-react';
import { ToggleGroup } from '@/components/buttons/ToggleGroup';
import { DateRangePicker, type DateRangeValue } from '@/components/forms/DateRangePicker';
import { TagsManager } from '@/components/forms/TagsManager';
import { cn } from '@/utils/cn';
import type { EntityType } from '@/types/generated/models/EntityType';

interface SearchFiltersBarProps {
  entityType: EntityType | 'all';
  onEntityTypeChange: (value: EntityType | 'all') => void;
  selectedTags: string[];
  onTagsChange: (tags: string[]) => void;
  dateRange: DateRangeValue | null;
  onDateRangeChange: (value: DateRangeValue | null) => void;
  datePickerVariant?: 'neutral-secondary' | 'neutral-tertiary';
  className?: string;
}

export function SearchFiltersBar({
  entityType,
  onEntityTypeChange,
  selectedTags,
  onTagsChange,
  dateRange,
  onDateRangeChange,
  datePickerVariant = 'neutral-tertiary',
  className,
}: SearchFiltersBarProps) {
  return (
    <div
      className={cn(
        'flex w-full shrink-0 flex-col items-start gap-3 rounded-md border-b border-solid border-neutral-border px-6 pb-2 md:flex-row md:items-center md:gap-1',
        className,
      )}
    >
      <div className="flex w-full flex-col items-start gap-2 md:w-auto md:flex-row md:items-center md:self-stretch">
        <span className="text-caption-bold font-caption-bold text-subtext-color">
          Filter:{' '}
        </span>
        <ToggleGroup value={entityType} onValueChange={(value) => value && onEntityTypeChange(value as EntityType | 'all')}>
          <ToggleGroup.Item icon={null} value="all" className="w-auto">
            All
          </ToggleGroup.Item>
          <ToggleGroup.Item icon={<Bell />} value="alert" className="w-auto">
            Alerts
          </ToggleGroup.Item>
          <ToggleGroup.Item icon={<NotebookPen />} value="case" className="w-auto">
            Cases
          </ToggleGroup.Item>
          <ToggleGroup.Item icon={<List />} value="task" className="w-auto">
            Tasks
          </ToggleGroup.Item>
        </ToggleGroup>
      </div>
      <div className="w-full md:min-w-[220px] md:flex-1">
        <TagsManager
          inline
          tags={selectedTags}
          onTagsChange={onTagsChange}
          placeholder="+ Add tags"
        />
      </div>
      <div className="w-full md:ml-auto md:w-auto">
        <DateRangePicker
          className="w-full md:w-auto"
          value={dateRange}
          onChange={onDateRangeChange}
          showAllTime={true}
          size="small"
          variant={datePickerVariant}
        />
      </div>
    </div>
  );
}

export default SearchFiltersBar;
