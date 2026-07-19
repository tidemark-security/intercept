"use client";

import React from "react";

import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
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

import { ListTree, User2 } from 'lucide-react';
type MenuCardTag = string | {
  tag: string;
  source?: "entity" | "timeline";
};

interface MenuCardRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "id" | "title"> {
  id?: React.ReactNode;
  title?: React.ReactNode;
  timestamp?: React.ReactNode;
  assignee?: React.ReactNode;
  tags?: string | MenuCardTag[] | null;
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
  leadingContent?: React.ReactNode;
  bodyContent?: React.ReactNode;
  showDescription?: boolean;
  description?: React.ReactNode;
  onTagClick?: (tag: string, mode: "include" | "exclude") => void;
  highlightedTags?: string[];
  className?: string;
}

function tagMatchesFilter(tag: string, filters: string[]) {
  const normalizedTag = tag.toLowerCase();
  return filters.some((filter) => filter.trim() && normalizedTag.includes(filter.trim().toLowerCase()));
}

function getTagValue(tag: MenuCardTag) {
  return typeof tag === "string" ? tag : tag.tag;
}

function getTagSource(tag: MenuCardTag) {
  return typeof tag === "string" ? "entity" : tag.source ?? "entity";
}

function getTagContent(tag: MenuCardTag) {
  const value = getTagValue(tag);
  if (getTagSource(tag) !== "timeline") {
    return value;
  }

  return (
    <span className="flex min-w-0 items-center gap-1">
      <IconWrapper className="h-3 w-3 flex-none text-current">
        <ListTree />
      </IconWrapper>
      <span className="truncate">{value}</span>
    </span>
  );
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
      leadingContent,
      bodyContent,
      showDescription = false,
      description,
      onTagClick,
      highlightedTags = [],
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
    const [isExcludeModifierActive, setIsExcludeModifierActive] = React.useState(false);

    React.useEffect(() => {
      if (!onTagClick) return;

      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.metaKey || event.ctrlKey) {
          setIsExcludeModifierActive(true);
        }
      };
      const handleKeyUp = (event: KeyboardEvent) => {
        if (!event.metaKey && !event.ctrlKey) {
          setIsExcludeModifierActive(false);
        }
      };
      const handleBlur = () => setIsExcludeModifierActive(false);

      window.addEventListener("keydown", handleKeyDown);
      window.addEventListener("keyup", handleKeyUp);
      window.addEventListener("blur", handleBlur);

      return () => {
        window.removeEventListener("keydown", handleKeyDown);
        window.removeEventListener("keyup", handleKeyUp);
        window.removeEventListener("blur", handleBlur);
      };
    }, [onTagClick]);

    const handleTagClick = React.useCallback(
      (event: React.MouseEvent, tag: string) => {
        if (!onTagClick) return;

        event.preventDefault();
        event.stopPropagation();
        onTagClick(tag, event.metaKey || event.ctrlKey ? "exclude" : "include");
      },
      [onTagClick],
    );

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
        variant={variant}
        className={className}
        ref={ref}
        {...otherProps}
      >
        <div className="flex w-full min-w-0 items-start gap-3">
          {leadingContent ? (
            <div className="flex h-6 w-6 flex-none items-center justify-center">
              {leadingContent}
            </div>
          ) : null}
          <div className="flex min-w-0 grow shrink basis-0 flex-col items-start gap-1">
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
                  // className="grayscale-[50%]"
                  />
                </div>
              </div>
            </div>
            {bodyContent ? (
              <div className="flex w-full min-w-0 flex-col gap-1 pt-1">
                {bodyContent}
              </div>
            ) : null}
          </div>
        </div>
        {tagList.length > 0 && (
          <div className="-mx-4 -mb-3 mt-2 w-[calc(100%+2rem)] border-t border-solid border-neutral-border bg-neutral-500/10 px-4 py-2">
            <div className="flex w-full items-center gap-1 overflow-hidden flex-nowrap">
              {tagList.map((tag, index) => {
                const tagValue = getTagValue(tag);
                const isTimelineTag = getTagSource(tag) === "timeline";
                const isHighlighted = tagMatchesFilter(tagValue, highlightedTags);

                return (
                  <Tag
                    key={`${getTagSource(tag)}-${tagValue}-${index}`}
                    tagText={getTagContent(tag)}
                    action={!isTimelineTag && onTagClick ? (isExcludeModifierActive ? "minus" : "plus") : undefined}
                    actionLabel={!isTimelineTag && onTagClick ? `${isExcludeModifierActive ? "Exclude" : "Include"} ${tagValue}` : undefined}
                    showAction={!isTimelineTag && Boolean(onTagClick)}
                    onAction={(event) => handleTagClick(event, tagValue)}
                    onClick={!isTimelineTag ? (event) => handleTagClick(event, tagValue) : undefined}
                    onMouseEnter={(event) => setIsExcludeModifierActive(event.metaKey || event.ctrlKey)}
                    onMouseMove={(event) => setIsExcludeModifierActive(event.metaKey || event.ctrlKey)}
                    p={isHighlighted ? "4" : "0"}
                    searchable={!isTimelineTag}
                    className="shrink-0"
                  />
                );
              })}
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
