"use client";

import React from "react";

import * as HoverCard from "@radix-ui/react-hover-card";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";
import { Badge } from "@/components/data-display/Badge";
import { Priority } from "@/components/misc/Priority";
import { State } from "@/components/misc/State";

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
    const isDarkTheme = resolvedTheme === "dark";

    return (
      <div
        className={cn(
          "group/6c3f1f95 flex w-full cursor-pointer flex-col flex-wrap items-center justify-between rounded-sm border border-solid border-neutral-border bg-neutral-0 px-4 py-3 hover:border hover:border-solid hover:border-brand-primary",
          {
            "border border-solid border-accent-1-primary":
              variant === "selected",
          },
          className
        )}
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
                  className={cn(
                    "grow shrink-0 basis-0 whitespace-nowrap text-caption-bold font-caption-bold text-subtext-color",
                    {
                      "group-hover/6c3f1f95:text-brand-700": isDarkTheme,
                      "group-hover/6c3f1f95:text-brand-800": !isDarkTheme,
                      "text-accent-1-700": variant === "selected" && isDarkTheme,
                      "text-accent-1-900": variant === "selected" && !isDarkTheme,
                    }
                  )}
                >
                  {id}
                </span>
              ) : null}
              {timestamp ? (
                <span
                  className={cn(
                    "grow shrink-0 basis-0 whitespace-nowrap text-caption font-caption text-subtext-color text-right",
                    {
                      "group-hover/6c3f1f95:text-brand-700": isDarkTheme,
                      "group-hover/6c3f1f95:text-brand-800": !isDarkTheme,
                      "text-accent-1-700": variant === "selected" && isDarkTheme,
                      "text-accent-1-900": variant === "selected" && !isDarkTheme,
                    }
                  )}
                >
                  {timestamp}
                </span>
              ) : null}
            </div>
            <div className="flex w-full flex-wrap items-center justify-center gap-2 pr-2">
              {title ? (
                <span
                  className={cn(
                    "line-clamp-1 min-w-[240px] grow shrink-0 basis-0 text-body-bold font-body-bold",
                    {
                      "text-[#fafafaff] group-hover/6c3f1f95:text-brand-400": isDarkTheme,
                      "text-default-font group-hover/6c3f1f95:text-brand-800": !isDarkTheme,
                      "text-accent-1-400": variant === "selected" && isDarkTheme,
                      "text-accent-1-900": variant === "selected" && !isDarkTheme,
                    }
                  )}
                >
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
                  "group-hover/6c3f1f95:text-brand-800": !isDarkTheme,
                },
                { inline: showDescription }
              )}
            >
              {description}
            </span>
          ) : null}
        </div>
      </div>
    );
  }
);

export const MenuCard = MenuCardRoot;
