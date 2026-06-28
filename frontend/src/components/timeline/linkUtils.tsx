/**
 * Timeline Card Link Utilities
 * 
 * Utilities for rendering backend-resolved link template actions for timeline cards.
 */

import React from 'react';
import { useResolvedLinkTemplates } from '@/hooks/useUserLinkTemplates';
import { LinkButton } from './LinkButton';

export function ResolvedLinkButtons({
  item,
  entityType,
  customButtons,
  options,
}: {
  item: Record<string, unknown>;
  entityType?: 'alert' | 'case' | 'task';
  customButtons?: React.ReactNode | null;
  options?: {
    variant?: 'neutral-tertiary' | 'brand-tertiary' | 'destructive-tertiary';
    size?: 'small' | 'medium' | 'large';
    className?: string;
  };
}) {
  const { data: links = [] } = useResolvedLinkTemplates(item, true, {
    surface: 'timeline_item',
    entity_type: entityType,
  });

  if (!customButtons && links.length === 0) {
    return null;
  }

  const linkButtons = links.length > 0 ? (
    <div className="flex items-center gap-1">
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
  ) : null;

  if (!customButtons) {
    return linkButtons;
  }

  if (!linkButtons) {
    return (
      <div className="flex w-full items-center justify-end">
        {customButtons}
      </div>
    );
  }

  return (
    <div className="flex w-full items-center gap-2">
      {linkButtons}
      <div className="ml-auto flex items-center gap-2">
        {customButtons}
      </div>
    </div>
  );
}
