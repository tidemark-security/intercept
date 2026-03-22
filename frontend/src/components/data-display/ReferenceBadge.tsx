/**
 * ReferenceBadge component for rendering inline timeline references as clickable badge-links.
 * 
 * Renders as an <a> tag styled as a badge with:
 * - Link icon for same-entity references
 * - ExternalLink icon for cross-entity references
 * - Grayed out styling for invalid references
 */

import React from 'react';
import { LinkBadge } from './LinkBadge';

interface ParsedReference {
  href: string;
  timelineId: string;
  isCrossEntity?: boolean;
  entityId?: string;
}

export interface ReferenceBadgeProps {
  /** The parsed reference data */
  reference: ParsedReference;
  /** Whether the reference is valid (target exists in DOM) */
  isValid?: boolean;
  /** Additional class names */
  className?: string;
}

/**
 * Get display text for a reference.
 * Shows entity ID prefix for cross-entity refs, truncated timeline ID otherwise.
 */
function getDisplayText(reference: ParsedReference): string {
  if (reference.isCrossEntity && reference.entityId) {
    return `${reference.entityId}:${reference.timelineId}`;
  }
  return reference.timelineId;
}

export function ReferenceBadge({ 
  reference, 
  isValid = true,
  className,
}: ReferenceBadgeProps) {
  const displayText = getDisplayText(reference);
  
  return (
    <LinkBadge
      href={reference.href}
      isValid={isValid}
      title={reference.isCrossEntity 
        ? `View timeline item in ${reference.entityId}` 
        : 'Jump to timeline item'
      }
      className={className}
    >
      {displayText}
    </LinkBadge>
  );
}
