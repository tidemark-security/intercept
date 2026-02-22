/**
 * Timeline Card Link Utilities
 * 
 * Utilities for generating action buttons from link templates for timeline cards.
 */

import React from 'react';
import type { LinkTemplate } from '@/utils/linkTemplates';
import { generateLinks, generateAutoLinks } from '@/utils/linkTemplates';
import { LinkButton } from './LinkButton';

/**
 * Generate action buttons from link templates
 * 
 * Takes an array of link templates and a timeline item, then generates
 * LinkButton components for each applicable template.
 * 
 * @param templates - Array of link template configurations
 * @param item - Timeline item data
 * @param options - Optional configuration for button rendering
 * @returns React node containing action buttons, or null if none
 * 
 * @example
 * ```tsx
 * const templates = [
 *   {
 *     id: 'email',
 *     icon: <FeatherMail />,
 *     tooltip: 'Email {{contact_email}}',
 *     urlTemplate: 'mailto:{{contact_email}}',
 *     condition: (item) => !!item.contact_email,
 *   }
 * ];
 * 
 * const buttons = generateLinkButtons(templates, timelineItem);
 * 
 * // Use in createTimelineCard:
 * const cardProps = createTimelineCard(item, {
 *   actionButtons: buttons,
 * });
 * ```
 */
export function generateLinkButtons(
  templates: LinkTemplate[],
  item: any,
  options?: {
    variant?: 'neutral-tertiary' | 'brand-tertiary' | 'destructive-tertiary';
    size?: 'small' | 'medium' | 'large';
    className?: string;
  }
): React.ReactNode | null {
  const links = generateLinks(templates, item);
  
  if (links.length === 0) {
    return null;
  }

  return (
    <div className="flex gap-1">
      {links.map((link) => (
        <LinkButton
          key={link.id}
          href={link.url}
          icon={link.icon}
          tooltip={link.tooltip}
          variant={options?.variant}
          size={options?.size}
          className={link.className || options?.className}
        />
      ))}
    </div>
  );
}

/**
 * Combine custom action buttons with generated link buttons
 * 
 * @param customButtons - Custom action buttons (e.g., edit, delete)
 * @param linkTemplates - Array of link templates
 * @param item - Timeline item data
 * @returns Combined action buttons
 */
export function combineActionButtons(
  customButtons: React.ReactNode | null,
  linkTemplates: LinkTemplate[],
  item: any
): React.ReactNode | null {
  const linkButtons = generateLinkButtons(linkTemplates, item);
  
  if (!customButtons && !linkButtons) {
    return null;
  }
  
  if (!customButtons) {
    return linkButtons;
  }
  
  if (!linkButtons) {
    return customButtons;
  }
  
  // Both exist - combine them
  return (
    <div className="flex gap-1">
      {customButtons}
      {linkButtons}
    </div>
  );
}

/**
 * Automatically generate link buttons based on item fields
 * 
 * Detects which link templates apply to an item based on the fields present
 * in the item, then generates LinkButton components for each applicable template.
 * 
 * @param templates - Array of available link templates (from API)
 * @param item - Timeline item data
 * @param options - Optional configuration for button rendering
 * @returns React node containing action buttons, or null if none
 * 
 * @example
 * ```tsx
 * // Automatically detect and generate links from API templates
 * const buttons = generateAutoLinkButtons(apiTemplates, item);
 * 
 * const cardProps = createTimelineCard(item, {
 *   actionButtons: buttons,
 * });
 * ```
 */
export function generateAutoLinkButtons(
  templates: LinkTemplate[],
  item: any,
  options?: {
    variant?: 'neutral-tertiary' | 'brand-tertiary' | 'destructive-tertiary';
    size?: 'small' | 'medium' | 'large';
    className?: string;
  }
): React.ReactNode | null {
  const links = generateAutoLinks(templates, item);
  
  if (links.length === 0) {
    return null;
  }

  return (
    <div className="flex gap-1">
      {links.map((link) => (
        <LinkButton
          key={link.id}
          href={link.url}
          icon={link.icon}
          tooltip={link.tooltip}
          variant={options?.variant}
          size={options?.size}
          className={link.className || options?.className}
        />
      ))}
    </div>
  );
}

/**
 * Combine custom buttons with automatically detected link buttons
 * 
 * @param customButtons - Custom action buttons (e.g., edit, delete)
 * @param templates - Array of available link templates (from API)
 * @param item - Timeline item data
 * @returns Combined action buttons
 * 
 * @example
 * ```tsx
 * const customButtons = (
 *   <IconButton icon={<FeatherEdit />} onClick={handleEdit} />
 * );
 * 
 * const allButtons = combineWithAutoLinks(customButtons, apiTemplates, item);
 * ```
 */
export function combineWithAutoLinks(
  customButtons: React.ReactNode | null,
  templates: LinkTemplate[],
  item: any
): React.ReactNode | null {
  const autoLinkButtons = generateAutoLinkButtons(templates, item);
  
  if (!customButtons && !autoLinkButtons) {
    return null;
  }
  
  if (!customButtons) {
    return autoLinkButtons;
  }
  
  if (!autoLinkButtons) {
    return customButtons;
  }
  
  // Both exist - combine them
  return (
    <div className="flex gap-1">
      {customButtons}
      {autoLinkButtons}
    </div>
  );
}
