/**
 * Note Item Handler
 * 
 * Handler for NoteItem timeline items.
 * Notes display minimal card content since description is shown by parent timeline.
 */

import type { TimelineItem } from '@/types/timeline';
import type { NoteItem } from '@/types/generated/models/NoteItem';
import { getTimelineIcon } from '@/utils/timelineIcons';
import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

/**
 * Check if item is a NoteItem
 */
export function isNoteItem(item: TimelineItem): item is TimelineItem & NoteItem {
  return item.type === 'note';
}

/**
 * Handle NoteItem timeline items.
 * 
 * Field mapping:
 * - Title: "Note" (static)
 * - Line1: Description content (for standalone card rendering, e.g. search results)
 * - Icon: FeatherNotebookText
 * - Color: default (notes are neutral)
 * 
 * Note: In timeline view, the description may also be shown by the parent component,
 * but including it in line1 ensures the card renders meaningfully in search context.
 */
export function handleNoteItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isNoteItem(item)) {
    throw new Error('Item is not a NoteItem');
  }

  const Icon = getTimelineIcon('note');

  const IconComponent = Icon ? <Icon /> : undefined;

  return {
    title: 'Note',
    line1: item.description || undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
