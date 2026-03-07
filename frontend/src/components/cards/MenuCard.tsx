"use client";

import React from "react";

import * as HoverCard from "@radix-ui/react-hover-card";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { Badge } from "@/components/data-display/Badge";
import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";
import { parseISO8601 } from "@/utils/dateFilters";
import { formatTimestampForPreference } from "@/utils/timezonePreference";
import {
  getMenuCardMetaClassName,
  getMenuCardTitleClassName,
  MenuCardBase,
} from "@/components/cards/MenuCardBase";

import { Tag, User2 } from 'lucide-react';
interface MenuCardRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "id" | "title"> {
  id?: React.ReactNode;
  title?: React.ReactNode;
  timestamp?: React.ReactNode;
  assignee?: React.ReactNode;
  tags?: React.ReactNode;
  state?:
    | "closed"
    | "new"
    | "in_progress"
    | "escalated"
    | "closed_true_positive"
    | "closed_benign_positive"
    | "closed_false_positive"
    | "closed_unresolved"
    | "closed_duplicate"
    | "tsk_todo"
    | "tsk_in_progress"
    | "tsk_done";
  priority?:
    | "default"
    | "info"
    | "low"
    | "medium"
    | "high"
    | "critical"
    | "extreme";
  variant?: "default" | "selected";
  showDescription?: boolean;
  description?: React.ReactNode;
  className?: string;
}

const MenuCardRoot = React.forwardRef<HTMLDivElement, MenuCardRootProps>(
  function MenuCardRoot(
    {
      id,
      title,
      timestamp,
      assignee,
      tags,
      state = "closed",
      priority = "default",
      variant = "default",
      showDescription = false,
      description,
      className,
      ...otherProps
    }: MenuCardRootProps,
    ref
  ) {
    const { resolvedTheme } = useTheme();
    const { timezonePreference } = useTimezonePreference();
    const isDarkTheme = resolvedTheme === "dark";
    const formattedTimestamp = React.useMemo(() => {
      if (typeof timestamp !== "string") {
        return timestamp;
      }

      const parsed = parseISO8601(timestamp);
      if (!parsed) {
        return timestamp;
      }

      return formatTimestampForPreference(parsed, timezonePreference);
    }, [timestamp, timezonePreference]);

    return (
      <MenuCardBase
        isDarkTheme={isDarkTheme}
        variant={variant}
        className={className}
        ref={ref}
        {...otherProps}
      >
        <div
          className={cn(
            "flex w-full flex-wrap items-center justify-between",
            { "flex-row flex-wrap justify-between": showDescription }
          )}
        >
          <div className="flex grow shrink-0 basis-0 flex-col flex-wrap items-start">
            <div className="flex flex-wrap items-start gap-4">
              {id ? (
                <span
                  className={getMenuCardMetaClassName(
                    isDarkTheme,
                    variant,
                    "grow shrink-0 basis-0 whitespace-nowrap text-caption-bold font-caption-bold"
                  )}
                >
                  {id}
                </span>
              ) : null}
              {formattedTimestamp ? (
                <span
                  className={getMenuCardMetaClassName(
                    isDarkTheme,
                    variant,
                    "grow shrink-0 basis-0 whitespace-nowrap text-caption text-right"
                  )}
                >
                  {formattedTimestamp}
                </span>
              ) : null}
            </div>
            <div className="flex w-full flex-wrap items-center justify-center gap-2 pr-2">
              {title ? (
                <span className={getMenuCardTitleClassName(isDarkTheme, variant)}>
                  {title}
                </span>
              ) : null}
            </div>
          </div>
          <div className="flex grow shrink-0 basis-0 flex-wrap items-center gap-2 px-1 py-1">
            <div className="flex grow shrink-0 basis-0 items-center justify-end gap-2">
              <Badge
                className="h-6 min-w-[128px] grow shrink-0 basis-0"
                variant="neutral"
                icon={<User2 />}
                iconRight={null}
              >
                {assignee}
              </Badge>
              <HoverCard.Root>
                <HoverCard.Trigger asChild={true}>
                  <Badge
                    variant="neutral"
                    icon={<Tag />}
                    iconRight={null}
                  />
                </HoverCard.Trigger>
                <HoverCard.Portal>
                  <HoverCard.Content
                    side="bottom"
                    align="center"
                    sideOffset={4}
                    asChild={true}
                  >
                    <div className="flex max-w-[288px] flex-col items-start gap-1 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-3 shadow-lg">
                      <div className="flex w-full flex-col items-start gap-2">
                        <div className="flex w-full items-center gap-2">
                          <span className="text-body-bold font-body-bold text-default-font">
                            Tags
                          </span>
                        </div>
                        <div className="flex w-full flex-wrap items-center gap-1 rounded-md bg-neutral-100 px-1 py-1">
                          {tags ? (
                            <span className="line-clamp-4 break-words text-caption-bold font-caption-bold text-default-font">
                              {tags}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </HoverCard.Content>
                </HoverCard.Portal>
              </HoverCard.Root>
              <State
                state={state}
              />
              <Priority
                priority={
                  priority === "extreme"
                    ? "extreme"
                    : priority === "critical"
                    ? "critical"
                    : priority === "high"
                    ? "high"
                    : priority === "medium"
                    ? "medium"
                    : priority === "low"
                    ? "low"
                    : undefined
                }
                size="mini"
                className="saturate-0"
              />
            </div>
          </div>
        </div>
        <div
          className={cn(
            "hidden w-full flex-wrap items-center justify-between group-hover/6c3f1f95:hidden",
            { "flex group-hover/6c3f1f95:flex": showDescription }
          )}
        >
          {description ? (
            <span
              className={cn(
                "line-clamp-2 hidden h-8 whitespace-pre-wrap text-caption font-caption text-subtext-color group-hover/6c3f1f95:inline",
                {
                  "group-hover/6c3f1f95:text-brand-primary": isDarkTheme,
                },
                { inline: showDescription }
              )}
            >
              {description}
            </span>
          ) : null}
        </div>
      </MenuCardBase>
    );
  }
);

export const MenuCard = MenuCardRoot;
