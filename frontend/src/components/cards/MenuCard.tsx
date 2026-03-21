"use client";

import React from "react";

import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { Badge } from "@/components/data-display/Badge";
import { Tag } from "@/components/data-display/Tag";
import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";
import { parseISO8601 } from "@/utils/dateFilters";
import { formatTimestampForPreference } from "@/utils/timezonePreference";
import {
  getMenuCardMetaClassName,
  getMenuCardTitleClassName,
  MenuCardBase,
} from "@/components/cards/MenuCardBase";

import { User2 } from 'lucide-react';
interface MenuCardRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "id" | "title"> {
  id?: React.ReactNode;
  title?: React.ReactNode;
  timestamp?: React.ReactNode;
  assignee?: React.ReactNode;
  tags?: string | string[] | null;
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

    const tagList = React.useMemo(() => {
      if (!tags) return [];
      const list = Array.isArray(tags)
        ? tags
        : typeof tags === 'string'
        ? tags.split(';').map((t) => t.trim()).filter(Boolean)
        : [];
      return list;
    }, [tags]);

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

              <State
                state={state}
                variant="mini"
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
        {tagList.length > 0 && (
          <div className="-mx-4 -mb-3 mt-2 w-[calc(100%+2rem)] border-t border-solid border-neutral-border bg-neutral-500/10 px-4 py-2">
            <div className="flex w-full items-center gap-1 overflow-hidden flex-nowrap">
              {tagList.map((tag, index) => (
                <Tag
                  key={`${tag}-${index}`}
                  tagText={tag}
                  showDelete={false}
                  p="0"
                  className="shrink-0"
                />
              ))}
            </div>
          </div>
        )}
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
