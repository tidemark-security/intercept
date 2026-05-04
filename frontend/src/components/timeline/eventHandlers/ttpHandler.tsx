/**
 * TTP Item Handler
 *
 * Handler for TTPItem (Tactics, Techniques, and Procedures) timeline items.
 * TTPs display MITRE ATT&CK framework information.
 */

import React from 'react';

import MarkdownContent from '@/components/data-display/MarkdownContent';
import { TimelineDescriptionBlock } from '@/components/timeline/TimelineDescriptionBlock';
import type { TimelineItem } from '@/types/timeline';
import type { TTPItem } from '@/types/generated/models/TTPItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { ChevronDown, ChevronUp, Crosshair, FileText } from 'lucide-react';

const COLLAPSED_MITRE_DESCRIPTION_HEIGHT = 48;

function ExpandableMitreDescription({ content }: { content: string }) {
  const contentRef = React.useRef<HTMLDivElement | null>(null);
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [isOverflowing, setIsOverflowing] = React.useState(false);

  React.useEffect(() => {
    const element = contentRef.current;

    if (!element) {
      return;
    }

    const updateOverflow = () => {
      setIsOverflowing(element.scrollHeight > COLLAPSED_MITRE_DESCRIPTION_HEIGHT + 1);
    };

    updateOverflow();

    const resizeObserver = new ResizeObserver(() => {
      updateOverflow();
    });

    resizeObserver.observe(element);

    return () => {
      resizeObserver.disconnect();
    };
  }, [content, isExpanded]);

  return (
    <div className="relative min-w-0 flex-1">
      <div
        className={isExpanded ? 'min-w-0 pr-8' : 'max-h-12 min-w-0 overflow-hidden pr-8'}
      >
        <div ref={contentRef} className="min-w-0">
          <MarkdownContent
            content={content}
            className="min-w-0 text-subtext-color [&_li]:my-0 [&_li]:text-caption [&_li]:font-caption [&_ol]:my-0 [&_ol]:text-caption [&_p]:my-2 [&_p]:text-caption [&_p]:font-caption [&_ul]:my-0 [&_ul]:text-caption"
            linkStyle="inline"
          />
        </div>
      </div>
      {isOverflowing ? (
        <div className={isExpanded ? 'absolute right-0 top-0 z-10' : 'pointer-events-none absolute inset-x-0 bottom-0 flex justify-end bg-gradient-to-t from-default-background/70 via-default-background/35 to-transparent pl-8 pt-4'}>
          <button
            type="button"
            className="pointer-events-auto flex h-6 w-6 items-center justify-center rounded-sm border border-neutral-border bg-default-background text-subtext-color transition hover:text-default-font"
            aria-label={isExpanded ? 'Collapse MITRE description' : 'Expand MITRE description'}
            onClick={() => setIsExpanded(current => !current)}
          >
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Check if item is a TTPItem
 */
export function isTTPItem(item: TimelineItem): item is TimelineItem & TTPItem {
  return item.type === 'ttp';
}

/**
 * Handle TTPItem timeline items.
 * 
 * Field mapping:
 * - Line1: Tactic (e.g., "Execution")
 * - Body: Full MITRE ATT&CK description with markdown links
 * - Line2: User notes (if present)
 * - Icon: FeatherTarget
 * - Color: default (TTPs are neutral threat intelligence)
 */
export function handleTTPItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isTTPItem(item)) {
    throw new Error('Item is not a TTPItem');
  }

  const Icon = getTimelineIcon('ttp');
  const IconComponent = Icon ? <Icon /> : undefined;

  const mitreId = item.mitre_id;
  const ttpTitle = item.title;
  const cardTitle = mitreId && ttpTitle
    ? `${mitreId}: ${ttpTitle}`
    : mitreId
      ? mitreId
      : ttpTitle
        ? ttpTitle
        : 'TTP';

  const mitreDescriptionBlock = item.mitre_description ? (
    <div className="flex w-full items-start gap-2 overflow-hidden">
      <span className="flex-none pt-0.5 text-body font-body text-subtext-color" aria-hidden="true">
        <FileText />
      </span>
      <ExpandableMitreDescription content={item.mitre_description} />
    </div>
  ) : undefined;

  const hasTags = !!item.tags?.length;
  const analystDescriptionBlock = item.description || hasTags || options.actionButtons ? (
    <TimelineDescriptionBlock actionButtons={options.actionButtons} tags={item.tags} className="mt-auto">
      {item.description ? (
        <MarkdownContent
          content={item.description}
          className="min-w-0 text-default-font"
        />
      ) : null}
    </TimelineDescriptionBlock>
  ) : undefined;

  const cardChildren = mitreDescriptionBlock || analystDescriptionBlock ? (
    <div className="flex w-full flex-col gap-3">
      {mitreDescriptionBlock}
      {analystDescriptionBlock}
    </div>
  ) : undefined;

  return {
    title: cardTitle,
    line1: item.tactic || undefined,
    line1Icon: item.tactic ? <Crosshair /> : undefined,
    children: cardChildren,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    _item: item,
  };
}
