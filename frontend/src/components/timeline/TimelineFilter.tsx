import React, { useMemo } from 'react';
import { ToggleGroup } from '@/components/buttons/ToggleGroup';
import type { TimelineItem } from '@/types/timeline';
import { PICERL_STAGES, type PICERLStage } from '@/types/caseTemplates';
import { getPicerlStageIcon, getPicerlStageLabels } from '@/components/misc/PicerlStage';
import { AdaptiveToggleLabel } from '@/components/timeline/AdaptiveToggleLabel';
import { getTimelineItemIcon, getTimelineItemLabel } from '@/utils/timelineMapping';
import { getTimelineItems } from '@/utils/timelineHelpers';
import { IconWrapper } from '@/utils/IconWrapper';
import { cn } from '@/utils/cn';
import { Tooltip } from '@/components/overlays/Tooltip';

import { ArrowDown, ArrowUp, Asterisk, Clock, Edit3, Group, Maximize2, Minimize2, RotateCcw, Ungroup } from 'lucide-react';
export type SortOption = 'created_at' | 'timestamp';
export type SortDirection = 'asc' | 'desc';

const DEFAULT_TIMELINE_SORT_BY: SortOption = 'timestamp';
const DEFAULT_TIMELINE_SORT_DIRECTION: SortDirection = 'asc';
const DEFAULT_TIMELINE_GROUP_SIMILAR = false;

type PicerlStageFilterProgress = {
  done: number;
  total: number;
};

const TIMELINE_TYPE_FILTER_ITEM_CLASS_NAME = "min-w-14 basis-24 flex-1 justify-center [&>span]:min-w-0 [&>span]:text-left";
const TIMELINE_PICERL_FILTER_ITEM_CLASS_NAME = "min-w-16 basis-28 flex-1 justify-center [&>span]:min-w-0 [&>span]:text-left";

function getSharedLabelIndex(keys: readonly string[], labelIndexes: Record<string, number>): number {
  return keys.reduce((sharedIndex, key) => Math.max(sharedIndex, labelIndexes[key] ?? 0), 0);
}

function isPICERLStage(value: unknown): value is PICERLStage {
  return typeof value === 'string' && (PICERL_STAGES as readonly string[]).includes(value);
}

function getTimelineTypeLabelCandidates(label: string): string[] {
  const words = label.trim().split(/\s+/).filter(Boolean);
  const compactLabel = words.length > 1 ? words[0] : label;

  return [label, compactLabel, ''];
}

function renderPicerlStageFilterTooltip(label: string, progress: PicerlStageFilterProgress) {
  const open = Math.max(progress.total - progress.done, 0);

  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-caption-bold font-caption-bold text-black">{label}</span>
      <span className="whitespace-nowrap text-caption font-caption text-black">
        {progress.done} complete · {open} open · {progress.total} total
      </span>
    </div>
  );
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

  /** Optional content shown before the filter/sort controls */
  leadingContent?: React.ReactNode;

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
  const button = (
    <button
      className={cn(
        "group/4d0dcf39 flex h-7 w-auto cursor-pointer items-center justify-center gap-2 rounded-md border border-transparent bg-transparent px-2 py-1 hover:bg-neutral-100 active:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-50 hover:disabled:bg-transparent active:disabled:bg-transparent",
        className,
      )}
      aria-label={commandTitle}
      disabled={disabled}
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

  if (!commandTitle) {
    return button;
  }

  return (
    <Tooltip.Provider delayDuration={0} skipDelayDuration={0}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          {button}
        </Tooltip.Trigger>
        <Tooltip.Content side="bottom" align="center" sideOffset={6}>
          {commandTitle}
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
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
  leadingContent,
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

  const picerlStageFilterProgress = useMemo(() => {
    const progress = PICERL_STAGES.reduce((acc, stage) => {
      acc[stage] = { done: 0, total: 0 };
      return acc;
    }, {} as Record<PICERLStage, PicerlStageFilterProgress>);

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

  const totalPicerlStageFilterProgress = useMemo(() => (
    PICERL_STAGES.reduce<PicerlStageFilterProgress>((total, stage) => {
      total.done += picerlStageFilterProgress[stage].done;
      total.total += picerlStageFilterProgress[stage].total;
      return total;
    }, { done: 0, total: 0 })
  ), [picerlStageFilterProgress]);
  const typeFilterLabelKeys = useMemo(() => ['all', ...availableTypes], [availableTypes]);
  const picerlFilterLabelKeys = useMemo(() => ['all', ...picerlStages], [picerlStages]);
  const [typeFilterLabelIndexes, setTypeFilterLabelIndexes] = React.useState<Record<string, number>>({});
  const [picerlFilterLabelIndexes, setPicerlFilterLabelIndexes] = React.useState<Record<string, number>>({});
  const typeFilterLabelIndex = getSharedLabelIndex(typeFilterLabelKeys, typeFilterLabelIndexes);
  const picerlFilterLabelIndex = getSharedLabelIndex(picerlFilterLabelKeys, picerlFilterLabelIndexes);
  const updateTypeFilterLabelIndex = React.useCallback((key: string, labelIndex: number) => {
    setTypeFilterLabelIndexes((current) => (
      current[key] === labelIndex ? current : { ...current, [key]: labelIndex }
    ));
  }, []);
  const updatePicerlFilterLabelIndex = React.useCallback((key: string, labelIndex: number) => {
    setPicerlFilterLabelIndexes((current) => (
      current[key] === labelIndex ? current : { ...current, [key]: labelIndex }
    ));
  }, []);
  const filtersAreDefault =
    !selectedType &&
    !selectedPICERLStage &&
    sortBy === DEFAULT_TIMELINE_SORT_BY &&
    sortDirection === DEFAULT_TIMELINE_SORT_DIRECTION &&
    groupSimilar === DEFAULT_TIMELINE_GROUP_SIMILAR;
  const resetTimelineFilters = React.useCallback(() => {
    onTypeChange(undefined);
    onPICERLStageChange?.(undefined);
    onSortChange(DEFAULT_TIMELINE_SORT_BY, DEFAULT_TIMELINE_SORT_DIRECTION);
    onGroupSimilarChange?.(DEFAULT_TIMELINE_GROUP_SIMILAR);
  }, [onGroupSimilarChange, onPICERLStageChange, onSortChange, onTypeChange]);

  React.useEffect(() => {
    const resetAdaptiveLabelIndexes = () => {
      setTypeFilterLabelIndexes({});
      setPicerlFilterLabelIndexes({});
    };

    window.addEventListener('resize', resetAdaptiveLabelIndexes);
    return () => window.removeEventListener('resize', resetAdaptiveLabelIndexes);
  }, []);

  return (
    <div className={`flex w-full items-start mobile:justify-center gap-2 flex-wrap mobile:border-0 border-t border-solid border-neutral-border pt-2 ${className || ''}`}>
      <div className="flex w-full min-w-0 flex-wrap items-start justify-start gap-2 mobile:justify-center">
        <TimelineFilterControlGroup>
          <div className="flex items-center gap-0.5 rounded-md border border-neutral-border bg-default-background p-0.5">
            <TimelineCommandButton
              disabled={disabled || filtersAreDefault}
              icon={<RotateCcw />}
              onClick={resetTimelineFilters}
            >
              Reset filters
            </TimelineCommandButton>
          </div>
        </TimelineFilterControlGroup>

        {leadingContent ? (
          <TimelineFilterControlGroup>
            {leadingContent}
          </TimelineFilterControlGroup>
        ) : null}

        <TimelineFilterControlGroup>
          <ToggleGroup
            value={sortBy}
            // variant="compact-button"
            labelDisplay="tooltip"
            className="border rounded-md border-neutral-border"
            onValueChange={(value: string) => {
              if (value === 'timestamp' || value === 'created_at') {
                onSortChange(value, sortDirection);
              }
            }}
          >
            <ToggleGroup.Item disabled={disabled} icon={<Clock />} value="timestamp" className="w-auto">
              Sort by Event Timestamp
            </ToggleGroup.Item>
            <ToggleGroup.Item disabled={disabled} icon={<Edit3 />} value="created_at" className="w-auto">
              Sort by Modification Time
            </ToggleGroup.Item>
          </ToggleGroup>
        </TimelineFilterControlGroup>

        <TimelineFilterControlGroup>
          <ToggleGroup
            value={sortDirection}
            // variant="compact-button"
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
              // variant="compact-button"
              labelDisplay="tooltip"
              className="border rounded-md border-neutral-border"
              onValueChange={(value: string) => {
                if (value === 'grouped' || value === 'ungrouped') {
                  onGroupSimilarChange(value === 'grouped');
                }
              }}
            >
              <ToggleGroup.Item disabled={disabled} icon={<Group />} value="grouped" className="w-auto">
                Group Similar Items
              </ToggleGroup.Item>
              <ToggleGroup.Item disabled={disabled} icon={<Ungroup />} value="ungrouped" className="w-auto">
                Ungroup Similar Items
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
                  Expand Timeline Items
                </TimelineCommandButton>
              ) : null}
              {onCollapseLinkedEntityCards ? (
                <TimelineCommandButton
                  disabled={disabled || !hasLinkedEntityCards}
                  icon={<Minimize2 />}
                  onClick={onCollapseLinkedEntityCards}
                >
                  Collapse Timeline Items
                </TimelineCommandButton>
              ) : null}
            </div>
          </TimelineFilterControlGroup>
        ) : null}

        {/* Type Filter Toggle Group - Horizontal */}
        <TimelineFilterControlGroup className="min-w-[min(100%,28rem)] flex-[999_1_28rem]">
          <ToggleGroup
            value={selectedType || 'all'}
            variant="compact-button"
            className="w-full flex-nowrap border rounded-md border-neutral-border"
            onValueChange={(value: string) => {
              onTypeChange(value === 'all' ? undefined : value);
            }}
          >
            {/* All option - always present */}
            <ToggleGroup.Item
              disabled={disabled}
              icon={<Asterisk />}
              value="all"
              aria-label="All Items"
              tooltip={typeFilterLabelIndex > 0 ? "All Items" : undefined}
              className={cn(TIMELINE_TYPE_FILTER_ITEM_CLASS_NAME, typeFilterLabelIndex >= 2 && "gap-0")}
            >
              <AdaptiveToggleLabel
                labels={getTimelineTypeLabelCandidates('All Items')}
                labelIndex={typeFilterLabelIndex}
                onLabelIndexChange={(labelIndex) => updateTypeFilterLabelIndex('all', labelIndex)}
                srLabel="All Items"
              />
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
                  aria-label={label}
                  tooltip={typeFilterLabelIndex > 0 ? label : undefined}
                  className={cn(TIMELINE_TYPE_FILTER_ITEM_CLASS_NAME, typeFilterLabelIndex >= 2 && "gap-0")}
                >
                  <AdaptiveToggleLabel
                    labels={getTimelineTypeLabelCandidates(label)}
                    labelIndex={typeFilterLabelIndex}
                    onLabelIndexChange={(labelIndex) => updateTypeFilterLabelIndex(type, labelIndex)}
                    srLabel={label}
                  />
                </ToggleGroup.Item>
              );
            })}
          </ToggleGroup>
        </TimelineFilterControlGroup>

        {onPICERLStageChange && picerlStages.length > 0 ? (
          <TimelineFilterControlGroup className="w-full">
            <ToggleGroup
              value={selectedPICERLStage || 'all'}
              variant="compact-button"
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
              <ToggleGroup.Item
                disabled={disabled}
                icon={<Asterisk />}
                value="all"
                aria-label={`All Task Stages ${totalPicerlStageFilterProgress.done}/${totalPicerlStageFilterProgress.total}`}
                tooltip={renderPicerlStageFilterTooltip("All Stages", totalPicerlStageFilterProgress)}
                className={TIMELINE_PICERL_FILTER_ITEM_CLASS_NAME}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <AdaptiveToggleLabel
                    labels={['All Task Stages', 'All']}
                    labelIndex={picerlFilterLabelIndex}
                    onLabelIndexChange={(labelIndex) => updatePicerlFilterLabelIndex('all', labelIndex)}
                    srLabel="All Task Stages"
                    className="flex-1"
                  />
                  <span className="text-caption font-caption opacity-80">
                    {totalPicerlStageFilterProgress.done}/{totalPicerlStageFilterProgress.total}
                  </span>
                </span>
              </ToggleGroup.Item>
              {picerlStages.map((stage) => {
                const Icon = getPicerlStageIcon(stage);
                const stageFilterLabels = getPicerlStageLabels(stage);
                const progress = picerlStageFilterProgress[stage];

                return (
                  <ToggleGroup.Item
                    disabled={disabled}
                    icon={<Icon />}
                    key={stage}
                    value={stage}
                    aria-label={`${stageFilterLabels[0]} ${progress.done}/${progress.total}`}
                    tooltip={renderPicerlStageFilterTooltip(stageFilterLabels[0], progress)}
                    className={TIMELINE_PICERL_FILTER_ITEM_CLASS_NAME}
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      <AdaptiveToggleLabel
                        labels={stageFilterLabels}
                        labelIndex={picerlFilterLabelIndex}
                        onLabelIndexChange={(labelIndex) => updatePicerlFilterLabelIndex(stage, labelIndex)}
                        srLabel={stageFilterLabels[0]}
                        className="flex-1"
                      />
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
