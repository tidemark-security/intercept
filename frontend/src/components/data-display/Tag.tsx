"use client";

import React from "react";

import { cn } from "@/utils/cn";

import { X } from 'lucide-react';
interface ConditionalDeleteButtonProps
  extends React.HTMLAttributes<HTMLDivElement> {
  mode?: "default" | "light" | "dark";
  className?: string;
}

const ConditionalDeleteButton = React.forwardRef<
  HTMLDivElement,
  ConditionalDeleteButtonProps
>(function ConditionalDeleteButton(
  { mode = "default", className, ...otherProps }: ConditionalDeleteButtonProps,
  ref
) {
  return (
    <div
      className={cn(
        "group/5b6b02a2 flex cursor-pointer items-center gap-2 hover:bg-[#ffffff33]",
        { "hover:bg-[#00000033]": mode === "dark" },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <X
        className={cn(
          "text-body font-body text-white",
          { "text-black": mode === "dark" }
        )}
      />
    </div>
  );
});

interface TagRootProps extends React.HTMLAttributes<HTMLDivElement> {
  tagText?: React.ReactNode;
  showDelete?: boolean;
  p?: "default" | "0" | "1" | "2" | "3" | "4" | "5";
  className?: string;
}

const TagRoot = React.forwardRef<HTMLDivElement, TagRootProps>(function TagRoot(
  {
    tagText,
    showDelete = false,
    p = "default",
    className,
    ...otherProps
  }: TagRootProps,
  ref
) {
  return (
    <div
      className={cn(
        "group/02c10a66 flex h-6 items-center justify-center gap-1 border bevel-br-md border-solid border-neutral-border bg-brand-100 px-2",
        {
          "bg-p5": p === "5",
          "bg-p4": p === "4",
          "bg-p3": p === "3",
          "bg-p2": p === "2",
          "bg-p1": p === "1",
          "bg-p0": p === "0",
        },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {tagText ? (
        <span
          className={cn(
            "line-clamp-1 grow shrink-0 basis-0 text-caption font-caption text-black text-center text-ellipsis overflow-hidden",
            {
              "text-neutral-0": p === "5",
              "text-brand-secondary": p === "4",
              "text-black": p === "3",
              "text-white": p === "2" || p === "1" || p === "0",
            }
          )}
        >
          {tagText}
        </span>
      ) : null}
      <div
        className={cn(
          "hidden h-4 w-4 flex-none items-center justify-center gap-1",
          { flex: showDelete }
        )}
      >
        <ConditionalDeleteButton
          className={cn("hidden", { flex: showDelete })}
          mode={
            p === "5"
              ? "dark"
              : p === "4"
              ? "dark"
              : p === "3"
              ? "dark"
              : p === "2"
              ? "light"
              : p === "1"
              ? "light"
              : p === "0"
              ? "light"
              : "dark"
          }
        />
      </div>
    </div>
  );
});

export const Tag = Object.assign(TagRoot, {
  ConditionalDeleteButton,
});
