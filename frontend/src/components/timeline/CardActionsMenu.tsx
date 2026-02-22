/**
 * CardActionsMenu
 * 
 * Three-dot dropdown menu for timeline card actions (flag, highlight, delete, edit).
 * This component is designed to be passed as actionButtons to BaseCard via the factory.
 * 
 * **Usage Pattern**: This menu should ONLY be visible on cards when they are collapsed/grouped
 * with other like cards. For single cards, the ActivityItem hover state with icon buttons
 * is the preferred interaction method.
 * 
 * Usage:
 * ```tsx
 * const menu = (
 *   <CardActionsMenu
 *     itemId="123"
 *     onFlag={handleFlag}
 *     onHighlight={handleHighlight}
 *     onDelete={handleDelete}
 *     onEdit={handleEdit}
 *   />
 * );
 * const cardProps = createTimelineCard(item, { actionButtons: menu });
 * ```
 */

import React, { useState, useRef, useEffect } from 'react';

import { IconWrapper } from '@/utils/IconWrapper';

import { Flag, Highlighter, MoreVertical, Pencil, Trash } from 'lucide-react';
export interface CardActionsMenuProps {
  /** Unique identifier for the timeline item */
  itemId: string;
  /** Handler for flagging/unflagging */
  onFlag?: (itemId: string) => void;
  /** Handler for highlighting/unhighlighting */
  onHighlight?: (itemId: string) => void;
  /** Handler for deleting */
  onDelete?: (itemId: string) => void;
  /** Handler for editing */
  onEdit?: (itemId: string) => void;
  /** Whether the item is read-only (hides all actions) */
  readOnly?: boolean;
}

interface MenuAction {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'danger';
}

export function CardActionsMenu({
  itemId,
  onFlag,
  onHighlight,
  onDelete,
  onEdit,
  readOnly = false,
}: CardActionsMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Don't render anything if read-only
  if (readOnly) {
    return null;
  }

  // Build menu actions based on available handlers
  const actions: MenuAction[] = [];

  if (onFlag) {
    actions.push({
      icon: <IconWrapper className="h-4 w-4"><Flag /></IconWrapper>,
      label: 'Flag',
      onClick: () => {
        onFlag(itemId);
        setIsOpen(false);
      },
    });
  }

  if (onHighlight) {
    actions.push({
      icon: <IconWrapper className="h-4 w-4"><Highlighter /></IconWrapper>,
      label: 'Highlight',
      onClick: () => {
        onHighlight(itemId);
        setIsOpen(false);
      },
    });
  }

  if (onEdit) {
    actions.push({
      icon: <IconWrapper className="h-4 w-4"><Pencil /></IconWrapper>,
      label: 'Edit',
      onClick: () => {
        onEdit(itemId);
        setIsOpen(false);
      },
    });
  }

  if (onDelete) {
    actions.push({
      icon: <IconWrapper className="h-4 w-4"><Trash /></IconWrapper>,
      label: 'Delete',
      onClick: () => {
        onDelete(itemId);
        setIsOpen(false);
      },
      variant: 'danger',
    });
  }

  // Don't render if no actions available
  if (actions.length === 0) {
    return null;
  }

  return (
    <div ref={menuRef} className="relative">
      {/* Three-dot menu button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="flex h-8 w-8 items-center justify-center rounded hover:bg-neutral-100 transition-colors"
        aria-label="Card actions"
      >
        <IconWrapper className="h-4 w-4 text-subtext-color">
          <MoreVertical />
        </IconWrapper>
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[160px] border bg-default-background border-neutral-border shadow-lg">
          <div className="py-1">
            {actions.map((action, index) => (
              <button
                key={index}
                onClick={(e) => {
                  e.stopPropagation();
                  action.onClick();
                }}
                className={`
                  flex w-full items-center gap-2 px-3 py-2 text-left text-sm
                  transition-colors
                  ${action.variant === 'danger' 
                    ? 'text-error-600 hover:bg-error-50' 
                    : 'text-default-font hover:bg-neutral-50'
                  }
                `}
              >
                {action.icon}
                <span>{action.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
