/**
 * Timeline Card Factory
 * 
 * Factory pattern for generating BaseCard component props from timeline items.
 * Supports all 17+ timeline item types with type-specific field mappings,
 * icons, and color systems.
 * 
 * Usage:
 * ```tsx
 * import { createTimelineCard } from '@/components/timeline/TimelineCardFactory';
 * 
 * const cardProps = createTimelineCard(timelineItem);
 * return <BaseCard {...cardProps} />;
 * ```
 */

import React from 'react';
import type { TimelineItem } from '@/types/timeline';
import { getTimelineIcon } from '@/utils/timelineIcons';
import { Badge } from '@/components/data-display/Badge';
import type { CopyTarget } from '@/components/cards/BaseCard';
import { LoaderCircle } from 'lucide-react';
import { combineWithAutoLinks } from './linkUtils';
import type { LinkTemplate } from '@/utils/linkTemplates';
import { CardActionsMenu } from './CardActionsMenu';
import { isTimelineItemEnrichmentActive } from './timelineUtils';

/**
 * Convert timeline item type to human-readable title.
 * 
 * @param type - Timeline item type (e.g., 'internal_actor', 'ttp', 'system')
 * @returns Human-readable title (e.g., 'Internal Actor', 'TTP', 'System')
 */
export function getTypeTitle(type: string | undefined): string {
  if (!type) return 'Unknown';
  
  // Special cases for acronyms and specific formatting
  const specialCases: Record<string, string> = {
    'ttp': 'TTP',
    'ip': 'IP Address',
    'url': 'URL',
    'dns': 'DNS',
    'api': 'API',
  };
  
  const lowerType = type.toLowerCase();
  if (specialCases[lowerType]) {
    return specialCases[lowerType];
  }
  
  // Convert snake_case to Title Case
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * System color values for BaseCard component
 */
export type CardSystem = 'default' | 'success' | 'warning' | 'error';

/**
 * Card size variants
 */
export type CardSize = 'x-large'| 'large' | 'medium' | 'small';

/**
 * Item characteristic definition for priority-based display
 */
export interface ItemCharacteristic {
  priority: number;
  color: CardSystem;
  accentText: string;
  accentIcon: React.ReactNode;
  badgeIcon: React.ReactNode;
  badgeText: string;
}

/**
 * Characteristics configuration for an item
 */
export interface CharacteristicsConfig<T = any> {
  /** Map of field names to their characteristic definitions */
  characteristics: Record<string, ItemCharacteristic>;
  /** Function to extract field values from the item */
  getFields?: (item: T) => Record<string, boolean>;
}

/**
 * Process characteristics to determine accent display and character flags
 */
export function processCharacteristics<T extends TimelineItem>(
  item: T,
  config?: CharacteristicsConfig<T>
): {
  color: CardSystem;
  accentText?: string;
  accentIcon?: React.ReactNode;
  characterFlags?: React.ReactNode;
} {
  if (!config) {
    return { color: 'default' };
  }

  const { characteristics, getFields } = config;
  const fields = getFields ? getFields(item) : (item as Record<string, any>);

  let highestPriority: ItemCharacteristic | null = null;
  const badges: React.ReactNode[] = [];

  // Check each characteristic and find the highest priority one that's true
  for (const [key, characteristic] of Object.entries(characteristics)) {
    if (fields[key] === true) {
      // Track highest priority for accent display
      if (!highestPriority || characteristic.priority < highestPriority.priority) {
        highestPriority = characteristic;
      }

      // Create badge for character flags
      badges.push(
        <Badge key={key} variant="neutral" icon={characteristic.badgeIcon}>
          {characteristic.badgeText}
        </Badge>
      );
    }
  }

  const result: {
    color: CardSystem;
    accentText?: string;
    accentIcon?: React.ReactNode;
    characterFlags?: React.ReactNode;
  } = {
    color: highestPriority?.color || 'default',
  };

  if (highestPriority) {
    result.accentText = highestPriority.accentText;
    result.accentIcon = highestPriority.accentIcon;
  }

  if (badges.length > 0) {
    result.characterFlags = (
      <div className="flex flex-wrap items-center gap-2">
        {badges}
      </div>
    );
  }

  return result;
}

/**
 * Options for card generation
 */
export interface CardFactoryOptions {
  /** Override card size (default: 'large') */
  size?: CardSize;
  /** Click handler for card interactions */
  onClick?: (item: TimelineItem) => void;
  /** Custom action buttons */
  actionButtons?: React.ReactNode;
  /** Link templates from API for auto-generating link buttons */
  linkTemplates?: LinkTemplate[];
  /** Characteristics configuration for automatic processing */
  characteristics?: CharacteristicsConfig;
  /** Alert ID for context-dependent features (e.g., attachment downloads) */
  alertId?: number | null;
  /** Entity type (alert, case, or task) for context-dependent features */
  entityType?: 'alert' | 'case' | 'task';
  
  // Action menu support (Option 3: Individual card actions)
  /** Item ID for action handlers */
  itemId?: string;
  /** Handler for flagging/unflagging */
  onFlag?: (itemId: string) => void;
  /** Handler for highlighting/unhighlighting */
  onHighlight?: (itemId: string) => void;
  /** Handler for deleting */
  onDelete?: (itemId: string) => void;
  /** Handler for editing */
  onEdit?: (itemId: string) => void;
  /** Whether the item is read-only (disables actions) */
  readOnly?: boolean;
  /** 
   * Enable action menu (three-dot dropdown) instead of relying on ActivityItem hover state.
   * Should ONLY be true when cards are grouped/collapsed together. For single cards,
   * the ActivityItem hover state is the preferred interaction method.
   */
  enableActionMenu?: boolean;
}

/**
 * Card configuration returned by factory
 */
export interface CardConfig {
  title?: React.ReactNode;
  baseIcon?: React.ReactNode;
  accentIcon?: React.ReactNode;
  accentText?: React.ReactNode;
  line1?: React.ReactNode;
  line2?: React.ReactNode;
  line3?: React.ReactNode;
  line4?: React.ReactNode;
  actionButtons?: React.ReactNode;
  system?: CardSystem;
  characterFlags?: React.ReactNode;
  line1Icon?: React.ReactNode;
  line2Icon?: React.ReactNode;
  line3Icon?: React.ReactNode;
  line4Icon?: React.ReactNode;
  size?: CardSize;
  enableCopyInteractions?: boolean;
  disableCopyTargets?: CopyTarget[];
  className?: string;
  children?: React.ReactNode;
  /** Original timeline item for reference */
  _item?: TimelineItem;
}

/**
 * Handler function type for timeline item types
 */
export type ItemHandler = (
  item: TimelineItem,
  options: CardFactoryOptions
) => CardConfig;

/**
 * Registry of item type handlers
 */
const handlerRegistry = new Map<string, ItemHandler>();

/**
 * Register a handler for a specific timeline item type.
 * 
 * Note: Handlers should set type-specific `title` values.
 * The factory only provides a generic fallback title when one is missing.
 * 
 * @param type - Timeline item type
 * @param handler - Handler function
 * 
 * @example
 * ```ts
 * registerHandler('task', (item, options) => ({
 *   title: item.task_human_id || 'Task',
 *   line1: item.description,
 *   line2: item.assignee,
 *   baseIcon: <FeatherCheckSquare />,
 *   system: 'default',
 * }));
 * ```
 */
export function registerHandler(type: string, handler: ItemHandler): void {
  handlerRegistry.set(type, handler);
}

/**
 * Generic fallback handler for unknown timeline item types.
 * Displays basic information and logs a warning.
 * Note: Title is set by the factory based on item type.
 */
function fallbackHandler(item: TimelineItem, options: CardFactoryOptions): CardConfig {
  const Icon = getTimelineIcon(item.type || 'note');

  // Log warning for unknown types
  if (process.env.NODE_ENV === 'development') {
    console.warn(
      `No handler registered for timeline item type: ${item.type}. Using fallback handler.`,
      item
    );
  }

  // Emit structured log in production for observability
  if (process.env.NODE_ENV === 'production') {
    console.log(
      JSON.stringify({
        level: 'warn',
        message: 'Unknown timeline item type',
        type: item.type,
        itemId: item.id,
        timestamp: new Date().toISOString(),
      })
    );
  }

  return {
    line1: item.description || 'No description available',
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}

/**
 * Create timeline card configuration from a timeline item.
 * 
 * This is the main factory function that dispatches to type-specific handlers
 * or falls back to a generic handler for unknown types.
 * 
 * Handlers should provide type-specific titles.
 * If a handler omits title, the factory applies a generic type-based fallback.
 * 
 * If linkTemplates are provided, auto-link buttons will be generated based on
 * item fields and combined with any custom action buttons.
 * 
 * @param item - Timeline item to render
 * @param options - Card generation options (size, onClick, custom buttons, templates)
 * @returns BaseCard component props
 * 
 * @example
 * ```tsx
 * const item: TimelineItem = { type: 'task', description: 'Investigation task' };
 * const cardProps = createTimelineCard(item);
 * return <BaseCard {...cardProps} />; // Title will be "Task"
 * 
 * // With API templates for auto-link generation
 * const cardProps = createTimelineCard(item, { linkTemplates: apiTemplates });
 * return <BaseCard {...cardProps} />; // Auto-generates email, phone, etc. buttons
 * ```
 */
export function createTimelineCard(
  item: TimelineItem,
  options: CardFactoryOptions = {}
): CardConfig {
  const handler = handlerRegistry.get(item.type || '') || fallbackHandler;
  const config = handler(item, options);

  if (isTimelineItemEnrichmentActive(item)) {
    config.baseIcon = <LoaderCircle className="animate-spin" />;
  }
  
  // Auto-generate link buttons if templates are provided
  let finalActionButtons = config.actionButtons || options.actionButtons;
  
  if (options.linkTemplates && options.linkTemplates.length > 0) {
    finalActionButtons = combineWithAutoLinks(
      finalActionButtons,
      options.linkTemplates,
      item
    );
  }
  
  // Generate action menu if enabled (Option 3: Individual card actions)
  if (options.enableActionMenu && options.itemId) {
    const actionMenu = (
      <CardActionsMenu
        itemId={options.itemId}
        onFlag={options.onFlag}
        onHighlight={options.onHighlight}
        onDelete={options.onDelete}
        onEdit={options.onEdit}
        readOnly={options.readOnly}
      />
    );
    
    // Combine with existing action buttons if any
    if (finalActionButtons) {
      finalActionButtons = (
        <div className="flex w-full items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {finalActionButtons}
          </div>
          {actionMenu}
        </div>
      );
    } else {
      finalActionButtons = (
        <div className="flex w-full items-center justify-end">
          {actionMenu}
        </div>
      );
    }
  }

  const cardTitle =
    typeof config.title === 'string'
      ? (config.title.trim() || getTypeTitle(item.type))
      : (config.title ?? getTypeTitle(item.type));

  return {
    ...config,
    title: cardTitle,
    actionButtons: finalActionButtons,
  };
}

/**
 * Get all registered handler types.
 * Useful for debugging and validation.
 */
export function getRegisteredTypes(): string[] {
  return Array.from(handlerRegistry.keys()).sort();
}

/**
 * Check if a handler is registered for a type.
 */
export function hasHandler(type: string): boolean {
  return handlerRegistry.has(type);
}

/**
 * Clear all registered handlers.
 * Primarily for testing.
 */
export function clearHandlers(): void {
  handlerRegistry.clear();
}
