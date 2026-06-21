import React, { useMemo } from 'react';
import { ToggleGroup } from '@/components/buttons/ToggleGroup';
import type { TimelineItem } from '@/types/timeline';
import { PICERL_STAGES, type PICERLStage } from '@/types/caseTemplates';
import { getTimelineItemIcon, getTimelineItemLabel } from '@/utils/timelineMapping';
import { getTimelineItems } from '@/utils/timelineHelpers';
import { IconWrapper } from '@/utils/IconWrapper';
import { cn } from '@/utils/cn';

import { ArrowDown, ArrowUp, Asterisk, BookOpen, ClipboardCheck, Clock, Edit3, Eye, Group, Maximize2, Minimize2, RotateCcw, ShieldCheck, ShieldOff, Ungroup } from 'lucide-react';
export type SortOption = 'created_at' | 'timestamp';
export type SortDirection = 'asc' | 'desc';

const PICERL_STAGE_LABELS: Record<PICERLStage, string> = {
  Preparation: 'Preparation',
  Identification: 'Identification',
  Containment: 'Containment',
  Eradication: 'Eradication',
  Recovery: 'Recovery',
  'Lessons Learned': 'Lessons Learned',
};

const PICERL_STAGE_ICONS: Record<PICERLStage, React.ComponentType> = {
  Preparation: ClipboardCheck,
  Identification: Eye,
  Containment: ShieldCheck,
  Eradication: ShieldOff,
  Recovery: RotateCcw,
  'Lessons Learned': BookOpen,
};

type PICERLStageProgress = {
  done: number;
  total: number;
};

function isPICERLStage(value: unknown): value is PICERLStage {
  return typeof value === 'string' && (PICERL_STAGES as readonly string[]).includes(value);
}

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

  /** Available PICERL stages to show as timeline filters. */
  picerlStages?: PICERLStage[];

  /** Currently selected PICERL stage filter. */
  selectedPICERLStage?: PICERLStage;

  /** Handler for PICERL stage filter changes. */
  onPICERLStageChange?: (stage: PICERLStage | undefined) => void;

  /** Whether there are visible linked entity cards that can be collapsed. */
  hasLinkedEntityCards?: boolean;

  /** Collapse all visible linked entity cards. */
  onCollapseLinkedEntityCards?: () => void;

  /** Expand all visible linked entity cards. */
  onExpandLinkedEntityCards?: () => void;
  
  /** Size variant for buttons (mobile vs desktop) */
  buttonSize?: 'small' | 'medium';
  
  /** Additional className for the container */
  className?: string;

  /** Optional content pinned to the right side of the filter row */
  rightContent?: React.ReactNode;

  /** Whether the filter controls are disabled */
  disabled?: boolean;
}

interface TimelineFilterControlGroupProps {
  label?: string;
  children: React.ReactNode;
  className?: string;
}

function TimelineFilterControlGroup({ label, children, className }: TimelineFilterControlGroupProps) {
  return (
    <div className={`flex min-w-0 flex-col ${label ? 'gap-1' : ''} ${className || ''}`}>
      {label ? <span className="text-caption-bold font-caption-bold text-default-font">{label}</span> : null}
      {children}
    </div>
  );
}

interface TimelineCommandButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ReactNode;
  children: React.ReactNode;
}

function TimelineCommandButton({
  icon,
  children,
  className,
  disabled = false,
  title,
  type = 'button',
  ...props
}: TimelineCommandButtonProps) {
  const commandTitle = title ?? (typeof children === 'string' || typeof children === 'number' ? String(children) : undefined);

  return (
    <button
      className={cn(
        "group/4d0dcf39 flex h-7 w-auto cursor-pointer items-center justify-center gap-2 rounded-md border border-transparent bg-transparent px-2 py-1 hover:bg-neutral-100 active:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-50 hover:disabled:bg-transparent active:disabled:bg-transparent",
        className,
      )}
      disabled={disabled}
      title={commandTitle}
      type={type}
      {...props}
    >
      <IconWrapper className="text-body font-body text-subtext-color group-hover/4d0dcf39:text-default-font group-active/4d0dcf39:text-default-font group-disabled/4d0dcf39:text-neutral-400">
        {icon}
      </IconWrapper>
      <span className="sr-only whitespace-nowrap text-caption-bold font-caption-bold text-subtext-color group-hover/4d0dcf39:text-default-font group-active/4d0dcf39:text-default-font group-disabled/4d0dcf39:text-neutral-400">
        {children}
      </span>
    </button>
  );
}

/**
 * TimelineFilter - Provides sort and filter controls for timeline items
 * 
 * Features:
 * - Segmented sort field control (time, modified)
 * - Segmented sort direction control (newest first, oldest first)
 * - Segmented grouping preference control
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
  groupSimilar = false,
  onGroupSimilarChange,
  picerlStages = [],
  selectedPICERLStage,
  onPICERLStageChange,
  hasLinkedEntityCards = false,
  onCollapseLinkedEntityCards,
  onExpandLinkedEntityCards,
  className,
  rightContent,
  disabled = false,
}: TimelineFilterProps) {
  // Derive unique item types from the timeline items
  const availableTypes = useMemo(() => {
    const types = new Set<string>();
    
    const addTypesFromItems = (itemList: TimelineItem[]) => {
      itemList.forEach((item) => {
        if (item.type) {
          types.add(item.type);
        }
        // Recursively check replies
        const replies = getTimelineItems({ timeline_items: item.replies ?? null });
        if (replies.length > 0) {
          addTypesFromItems(replies);
        }
      });
    };
    
    addTypesFromItems(items);
    return Array.from(types).sort();
  }, [items]);

  const picerlStageProgress = useMemo(() => {
    const progress = PICERL_STAGES.reduce((acc, stage) => {
      acc[stage] = { done: 0, total: 0 };
      return acc;
    }, {} as Record<PICERLStage, PICERLStageProgress>);

    items.forEach((item) => {
      const stage = (item as TimelineItem & { picerl_stage?: unknown }).picerl_stage;

      if (item.type !== 'task' || !isPICERLStage(stage)) {
        return;
      }

      progress[stage].total += 1;

      if (String((item as TimelineItem & { status?: unknown }).status ?? '').toUpperCase() === 'DONE') {
        progress[stage].done += 1;
      }
    });

    return progress;
  }, [items]);

  const totalPICERLProgress = useMemo(() => (
    PICERL_STAGES.reduce<PICERLStageProgress>((total, stage) => {
      total.done += picerlStageProgress[stage].done;
      total.total += picerlStageProgress[stage].total;
      return total;
    }, { done: 0, total: 0 })
  ), [picerlStageProgress]);

  return (
    <div className={`flex w-full items-start mobile:justify-center gap-2 flex-wrap mobile:border-0 border-t border-solid border-neutral-border pt-2 ${className || ''}`}>
      <div className="flex w-full min-w-0 flex-wrap items-start justify-start gap-2 mobile:justify-center">
        <TimelineFilterControlGroup>
          <ToggleGroup 
            value={sortBy}
            labelDisplay="tooltip"
            className="border rounded-md border-neutral-border"
            onValueChange={(value: string) => {
              if (value === 'timestamp' || value === 'created_at') {
                onSortChange(value, sortDirection);
              }
            }}
          >
            <ToggleGroup.Item disabled={disabled} icon={<Clock />} value="timestamp" className="w-auto">
              Time
            </ToggleGroup.Item>
            <ToggleGroup.Item disabled={disabled} icon={<Edit3 />} value="created_at" className="w-auto">
              Modified
            </ToggleGroup.Item>
          </ToggleGroup>
        </TimelineFilterControlGroup>

        <TimelineFilterControlGroup>
          <ToggleGroup
            value={sortDirection}
            labelDisplay="tooltip"
            className="border rounded-md border-neutral-border"
            onValueChange={(value: string) => {
              if (value === 'asc' || value === 'desc') {
                onSortChange(sortBy, value);
              }
            }}
          >
            <ToggleGroup.Item disabled={disabled} icon={<ArrowDown />} value="desc" className="w-auto">
              Newest first
            </ToggleGroup.Item>
            <ToggleGroup.Item disabled={disabled} icon={<ArrowUp />} value="asc" className="w-auto">
              Oldest first
            </ToggleGroup.Item>
          </ToggleGroup>
        </TimelineFilterControlGroup>

        {onGroupSimilarChange ? (
          <TimelineFilterControlGroup>
            <ToggleGroup
              value={groupSimilar ? 'grouped' : 'ungrouped'}
              labelDisplay="tooltip"
              className="border rounded-md border-neutral-border"
              onValueChange={(value: string) => {
                if (value === 'grouped' || value === 'ungrouped') {
                  onGroupSimilarChange(value === 'grouped');
                }
              }}
            >
              <ToggleGroup.Item disabled={disabled} icon={<Group />} value="grouped" className="w-auto">
                Grouped
              </ToggleGroup.Item>
              <ToggleGroup.Item disabled={disabled} icon={<Ungroup />} value="ungrouped" className="w-auto">
                Ungrouped
              </ToggleGroup.Item>
            </ToggleGroup>
          </TimelineFilterControlGroup>
        ) : null}

        {(onCollapseLinkedEntityCards || onExpandLinkedEntityCards) ? (
          <TimelineFilterControlGroup>
            <div className="flex items-center gap-0.5 rounded-md border border-neutral-border bg-default-background p-0.5">
              {onExpandLinkedEntityCards ? (
                <TimelineCommandButton
                  disabled={disabled || !hasLinkedEntityCards}
                  icon={<Maximize2 />}
                  onClick={onExpandLinkedEntityCards}
                >
                  Expand all
                </TimelineCommandButton>
              ) : null}
              {onCollapseLinkedEntityCards ? (
                <TimelineCommandButton
                  disabled={disabled || !hasLinkedEntityCards}
                  icon={<Minimize2 />}
                  onClick={onCollapseLinkedEntityCards}
                >
                  Collapse all
                </TimelineCommandButton>
              ) : null}
            </div>
          </TimelineFilterControlGroup>
        ) : null}

        {/* Type Filter Toggle Group - Horizontal */}
        <TimelineFilterControlGroup>
          <ToggleGroup
            value={selectedType || 'all'}
            className="border rounded-md border-neutral-border"
            onValueChange={(value: string) => {
              onTypeChange(value === 'all' ? undefined : value);
            }}
          >
            {/* All option - always present */}
            <ToggleGroup.Item disabled={disabled} icon={<Asterisk />} value="all" className='w-auto'>
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
        </TimelineFilterControlGroup>

        {onPICERLStageChange && picerlStages.length > 0 ? (
          <TimelineFilterControlGroup className="w-full">
            <ToggleGroup
              value={selectedPICERLStage || 'all'}
              variant="two-line-button"
              className="w-full border rounded-md border-neutral-border"
              onValueChange={(value: string) => {
                if (value === 'all') {
                  onPICERLStageChange(undefined);
                  return;
                }
                if ((PICERL_STAGES as string[]).includes(value)) {
                  onTypeChange('task');
                  onPICERLStageChange(value as PICERLStage);
                }
              }}
            >
              <ToggleGroup.Item disabled={disabled} icon={<Asterisk />} value="all" className="min-w-32 flex-1">
                <span className="flex min-w-0 flex-col items-start gap-0.5">
                  <span>All</span>
                  <span className="text-caption font-caption opacity-80">
                    {totalPICERLProgress.done}/{totalPICERLProgress.total}
                  </span>
                </span>
              </ToggleGroup.Item>
              {picerlStages.map((stage) => {
                const Icon = PICERL_STAGE_ICONS[stage];
                const progress = picerlStageProgress[stage];

                return (
                  <ToggleGroup.Item disabled={disabled} icon={<Icon />} key={stage} value={stage} className="min-w-32 flex-1">
                    <span className="flex min-w-0 flex-col items-start gap-0.5">
                      <span className="truncate">{PICERL_STAGE_LABELS[stage]}</span>
                      <span className="text-caption font-caption opacity-80">
                        {progress.done}/{progress.total}
                      </span>
                    </span>
                  </ToggleGroup.Item>
                );
              })}
            </ToggleGroup>
          </TimelineFilterControlGroup>
        ) : null}
      </div>
      {rightContent ? (
        <div className="ml-auto flex min-w-0 items-center justify-end pt-5 mobile:ml-0 mobile:w-full mobile:justify-center mobile:pt-0">
          {rightContent}
        </div>
      ) : null}
    </div>
  );
}

export default TimelineFilter;
