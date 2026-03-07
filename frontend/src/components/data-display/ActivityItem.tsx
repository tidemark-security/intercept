
"use client";

import React from "react";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";
import { Button } from "@/components/buttons/Button";
import { IconButton } from "@/components/buttons/IconButton";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { CopyableTimestamp } from "@/components/data-display/CopyableTimestamp";
import { RelativeTime } from "@/components/data-display/RelativeTime";

import { Check, Copy, Flag, Highlighter, MessageSquare, Pencil, Trash } from 'lucide-react';
interface ActivityItemRootProps extends React.HTMLAttributes<HTMLDivElement> {
  username?: React.ReactNode;
  action?: React.ReactNode;
  /** Display the timeline item ID/UUID with click-to-copy */
  displayItemId?: string | null;
  timestamp?: React.ReactNode;
  /** Raw timestamp value for event time */
  timestampValue?: string | null;
  /** Raw created_at value */
  createdAtValue?: string | null;
  /** Sort field to determine which timestamp to display */
  sortBy?: 'created_at' | 'timestamp';
  icon?: React.ReactNode;
  contents?: React.ReactNode;
  replies?: React.ReactNode;
  readOnly?: boolean;
  variant?: "default" | "primary" | "accent-1" | "accent-2" | "accent-3";
  flagged?: boolean;
  highlighted?: boolean;
  end?: boolean;
  replyEnabled?: boolean;
  itemId?: string;
  onFlag?: (itemId: string) => void;
  onHighlight?: (itemId: string) => void;
  onDelete?: (itemId: string) => void;
  onEdit?: (itemId: string) => void;
  onReply?: (itemId: string) => void;
  
  // Group-level action support (Option 1: Group header actions)
  /** Whether this represents a group of items */
  isGrouped?: boolean;
  /** Array of all item IDs in the group (for batch operations) */
  groupItemIds?: string[];
  /** Batch delete handler - called with array of IDs for grouped items */
  onDeleteBatch?: (itemIds: string[]) => void;
  
  className?: string;
}

const ActivityItemRoot = React.forwardRef<
  HTMLDivElement,
  ActivityItemRootProps
>(function ActivityItemRoot(
  {
    username,
    action,
    displayItemId,
    timestamp,
    timestampValue,
    createdAtValue,
    sortBy = 'timestamp',
    icon = <MessageSquare />,
    contents,
    replies,
    readOnly = false,
    variant = "default",
    flagged = false,
    highlighted = false,
    end = false,
    replyEnabled = false,
    itemId,
    onFlag,
    onHighlight,
    onDelete,
    onEdit,
    onReply,
    onDeleteBatch,
    isGrouped = false,
    groupItemIds = [],
    className,
    ...otherProps
  }: ActivityItemRootProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  // Use React state to track hover instead of CSS group modifiers to avoid nesting conflicts
  const [isHovered, setIsHovered] = React.useState(false);
  const [isMobile, setIsMobile] = React.useState(false);
  const [isItemIdHovered, setIsItemIdHovered] = React.useState(false);
  const [isItemIdCopied, setIsItemIdCopied] = React.useState(false);

  // Detect mobile screen size
  React.useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);
  
  // Calculate the timestamp to display based on sortBy
  const displayTimestampValue = React.useMemo(() => {
    if (sortBy === 'created_at') {
      return createdAtValue;
    }
    return timestampValue || createdAtValue;
  }, [sortBy, timestampValue, createdAtValue]);
  
  // Use timestamp prop if provided (for backward compatibility), otherwise use calculated value
  const displayTimestamp = timestamp || (displayTimestampValue ? <RelativeTime value={displayTimestampValue} /> : null);
  
  // Handle copying item ID to clipboard
  const handleCopyItemId = React.useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (displayItemId) {
      navigator.clipboard.writeText(displayItemId)
        .then(() => {
          setIsItemIdCopied(true);
          // Reset after 2 seconds
          setTimeout(() => setIsItemIdCopied(false), 2000);
        })
        .catch(err => {
          console.error('Failed to copy item ID:', err);
        });
    }
  }, [displayItemId]);
  
  // Handle group-level actions (Option 1: Call handler for all items in group)
  const handleGroupFlag = React.useCallback(() => {
    if (onFlag) {
      if (isGrouped && groupItemIds.length > 0) {
        // Call handler for each item in the group
        groupItemIds.forEach(id => onFlag(id));
      } else if (itemId) {
        // Single item
        onFlag(itemId);
      }
    }
  }, [onFlag, isGrouped, groupItemIds, itemId]);
  
  const handleGroupHighlight = React.useCallback(() => {
    if (onHighlight) {
      if (isGrouped && groupItemIds.length > 0) {
        groupItemIds.forEach(id => onHighlight(id));
      } else if (itemId) {
        onHighlight(itemId);
      }
    }
  }, [onHighlight, isGrouped, groupItemIds, itemId]);
  
  const handleGroupDelete = React.useCallback(() => {
    if (isGrouped && groupItemIds.length > 0 && onDeleteBatch) {
      // For grouped items, call batch delete handler with all IDs
      // This allows the parent to show a single confirmation dialog for all items
      onDeleteBatch(groupItemIds);
    } else if (itemId && onDelete) {
      // Single item - call delete handler (which will show confirmation dialog)
      onDelete(itemId);
    }
  }, [onDelete, onDeleteBatch, isGrouped, groupItemIds, itemId]);
  
  const handleGroupEdit = React.useCallback(() => {
    if (onEdit && itemId && !isGrouped) {
      // Only allow edit for single items, not groups
      onEdit(itemId);
    }
  }, [onEdit, itemId, isGrouped]);
  
  const handleReply = React.useCallback(() => {
    if (onReply && itemId) {
      onReply(itemId);
    }
  }, [onReply, itemId]);
  
  return (
    <div
      className={cn(
        "flex w-full items-start gap-4 hover:bg-neutral-0",
        {
          "bg-[image:repeating-linear-gradient(45deg,theme('colors.accent-1-primary-blush'),theme('colors.accent-1-primary-blush')_10px,transparent_10px,transparent_20px)]":
            highlighted,
          "bg-[image:repeating-linear-gradient(45deg,theme('colors.accent-2-primary-blush'),theme('colors.accent-2-primary-blush')_10px,transparent_10px,transparent_20px)]":
            flagged,
        },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <div
        className={cn(
          "flex w-8 flex-none flex-col items-center self-stretch",
          {
            [isDarkTheme ? "bg-accent-1-900" : "bg-accent-1-100"]:
              highlighted,
            [isDarkTheme ? "bg-accent-2-900" : "bg-accent-2-100"]: flagged,
          }
        )}
      >
        <div className="flex flex-col items-start">
          <div className="bg-default-background">
            <IconWithBackground
              variant={
                highlighted
                  ? "accent-1"
                  : flagged
                  ? "error"
                  : variant === "accent-3"
                  ? "accent-3"
                  : variant === "accent-2"
                  ? "accent-2"
                  : variant === "accent-1"
                  ? "accent-1"
                  : variant === "primary"
                  ? "brand"
                  : "neutral"
              }
              size="small"
              icon={icon}
              bevel={true}
            />
          </div>
          <IconWithBackground
            className={cn("hidden", {
              flex: highlighted,
            })}
            variant={highlighted ? "accent-1" : "neutral"}
            size="small"
            icon={
              highlighted ? <Highlighter /> : <MessageSquare />
            }
            bevel={false}
          />
          <IconWithBackground
            className={cn("hidden", { flex: flagged })}
            variant={flagged ? "error" : "neutral"}
            size="small"
            icon={flagged ? <Flag /> : <MessageSquare />}
            bevel={false}
          />
        </div>
        <div
          className={cn(
            "flex w-0.5 grow shrink-0 basis-0 flex-col items-start gap-2",
            {
              hidden: end,
              "bg-brand-primary": isDarkTheme,
              "bg-neutral-1000": !isDarkTheme,
              "bg-accent-1-300": highlighted,
              "bg-error-300": flagged,
            }
          )}
        />
      </div>
      <div
        className={cn(
          "flex grow shrink-0 basis-0 flex-col items-start self-stretch",
          { "bg-transparent": flagged }
        )}
      >
        <div
          className={cn(
            "flex w-full grow shrink-0 basis-0 flex-col items-start gap-0 border-r-2 border-solid border-neutral-200 pr-4",
            {
              "border-r-2 border-solid border-accent-3-primary":
                variant === "accent-3",
              "border-r-2 border-solid border-accent-2-primary":
                variant === "accent-2",
              "border-r-2 border-solid border-accent-1-primary":
                variant === "accent-1",
              "border-r-2 border-solid border-brand-primary":
                variant === "primary",
              "border-accent-1-900": highlighted,
              "border-accent-2-900": flagged,
            }
          )}
          onMouseEnter={() => {
            setIsHovered(true);
          }}
          onMouseLeave={(e) => {
            // Only clear hover if we're actually leaving the content div, not just moving between children
            const hasNodeSupport = typeof Node !== "undefined";
            const relatedTarget =
              hasNodeSupport && e.relatedTarget instanceof Node
                ? e.relatedTarget
                : null;

            if (!relatedTarget || !e.currentTarget.contains(relatedTarget)) {
              setIsHovered(false);
            }
          }}
        >
          <div className="flex w-full flex-wrap items-start gap-2 pt-2">
            <div className="flex grow shrink-0 basis-0 flex-wrap items-start gap-1">
              {username ? (
                <span className="text-body-bold font-body-bold text-default-font">
                  {username}
                </span>
              ) : null}
              {action ? (
                <span className="text-body font-body text-subtext-color">
                  {action}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-start justify-center gap-4 pt-0.5 pb-3">
              {displayItemId && !isMobile && (
                <div 
                  className="flex items-center gap-1 cursor-pointer"
                  onMouseEnter={() => setIsItemIdHovered(true)}
                  onMouseLeave={() => setIsItemIdHovered(false)}
                  onClick={handleCopyItemId}
                >
                  {isItemIdCopied ? (
                    <Check 
                      className="h-3 w-3 text-neutral-400 transition-opacity opacity-100"
                    />
                  ) : (
                    <Copy 
                      className={cn(
                        "h-3 w-3 text-neutral-400 transition-opacity",
                        { "opacity-0": !isItemIdHovered, "opacity-100": isItemIdHovered }
                      )}
                    />
                  )}
                  <span
                    className={cn(
                      "text-caption font-mono",
                      isDarkTheme ? "text-neutral-400 hover:text-neutral-500" : "text-neutral-600 hover:text-neutral-700"
                    )}
                  >
                    {displayItemId}
                  </span>
                </div>
              )}
              {displayTimestamp ? (
                <div className="flex items-center gap-2">
                  <CopyableTimestamp value={displayTimestampValue} showFull={false} variant="accent-1-left" />
                  <span className="text-caption font-caption text-subtext-color w-24 text-right shrink-0">
                    {displayTimestamp}
                  </span>
                </div>
              ) : null}
            </div>
          </div>
          {contents ? (
            <div className="flex w-full flex-col items-start">{contents}</div>
          ) : null}
          <div
            className={cn(
              "h-8",
                {
                  "hidden": !readOnly
                },
                {
                  "hidden": !!replies
                }
            )}
          ></div>
          <div
            className={cn(
              "flex h-16 w-full flex-none flex-col items-start justify-center",
                {
                  "hidden": readOnly
                }
            )}
          >
            <div
              className={cn(
                "w-full items-center justify-end gap-1 flex",
                {
                  "hidden": !(isHovered && !readOnly)
                }
              )}
            >
              {/* Reply button at leftmost position (only when enabled) */}
              {replyEnabled && (
                <Button 
                  size="small"
                  variant="neutral-tertiary"
                  aria-label="Reply"

                  icon={<MessageSquare />}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleReply();
                  }}
                >Reply</Button>
              )}

              <div className="flex h-px grow shrink-0 basis-0 flex-col items-center gap-2 bg-neutral-border" />
              <IconButton 
                size="small" 
                icon={<Flag />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleGroupFlag();
                }}
              />
              <IconButton 
                size="small" 
                icon={<Highlighter />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleGroupHighlight();
                }}
              />
              <IconButton 
                size="small" 
                icon={<Trash />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleGroupDelete();
                }}
              />
              {/* Hide edit button for grouped items */}
              {!isGrouped && (
                <IconButton 
                  size="small" 
                  icon={<Pencil />}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleGroupEdit();
                  }}
                />
              )}
            </div>
          </div>
        </div>
        {replies ? (
          <div className="flex w-full flex-col items-start">
            {replies}
          </div>
        ) : null}
      </div>
    </div>
  );
});

export const ActivityItem = ActivityItemRoot;
