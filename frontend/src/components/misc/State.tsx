
"use client";

import React from "react";







import { cn } from "@/utils/cn";

import { Check, CheckSquare, ChevronsUp, Mail, MailOpen, MinusSquare, Square } from 'lucide-react';
interface StateRootProps extends React.HTMLAttributes<HTMLDivElement> {
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
  variant?: "small" | "mini" | "maxi";
  className?: string;
}

const StateRoot = React.forwardRef<HTMLDivElement, StateRootProps>(
  function StateRoot(
    {
      state = "closed",
      variant = "small",
      className,
      ...otherProps
    }: StateRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "group/a7f5a586 flex h-6 w-24 items-center gap-1 rounded-md border border-solid border-neutral-border bg-neutral-50 px-2",
          {
            "h-16 w-full min-w-[176px] flex-col flex-nowrap items-start justify-center gap-2 px-2 py-2":
              variant === "maxi",
            "h-6 w-auto": variant === "mini",
          },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {state === "escalated" ? (
          <ChevronsUp
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        ) : state === "in_progress" ? (
          <MailOpen
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        ) : state === "new" ? (
          <Mail
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        ) : state === "tsk_todo" ? (
          <Square
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        ) : state === "tsk_in_progress" ? (
          <MinusSquare
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        ) : state === "tsk_done" ? (
          <CheckSquare
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        ) : (
          <Check
            className={cn(
              "text-body font-body text-neutral-700",
              { "text-heading-2 font-heading-2": variant === "maxi" }
            )}
          />
        )}
        <span
          className={cn(
            "grow shrink-0 basis-0 whitespace-nowrap text-caption font-caption text-neutral-700 text-center",
            {
              "font-['Saira'] text-[20px] font-[400] leading-[22px] tracking-normal text-left":
                variant === "maxi",
              hidden: variant === "mini",
            }
          )}
        >
          {state === "escalated"
            ? "Escalated"
            : state === "in_progress"
            ? "In Progress"
            : state === "new"
            ? "New"
            : state === "closed_true_positive"
            ? "Closed TP"
            : state === "closed_benign_positive"
            ? "Closed BP"
            : state === "closed_false_positive"
            ? "Closed FP"
            : state === "closed_unresolved"
            ? "Unresolved"
            : state === "closed_duplicate"
            ? "Duplicate"
            : state === "tsk_todo"
            ? "To Do"
            : state === "tsk_in_progress"
            ? "In Progress"
            : state === "tsk_done"
            ? "Done"
            : "Closed"}
        </span>
      </div>
    );
  }
);

export const State = StateRoot;
