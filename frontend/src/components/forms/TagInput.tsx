"use client";

import React from "react";

import { cn } from "@/utils/cn";
import { TextField } from "./TextField";
import { Tooltip } from "@/components/overlays/Tooltip";

import { Tags } from 'lucide-react';
interface TagInputRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "placeholder"> {
  label?: React.ReactNode;
  placeholder?: React.ReactNode;
  tags?: React.ReactNode;
  className?: string;
}

const TagInputRoot = React.forwardRef<HTMLDivElement, TagInputRootProps>(
  function TagInputRoot(
    { label, placeholder, tags, className, ...otherProps }: TagInputRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "flex w-full flex-col items-start gap-4",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <TextField
          className="h-auto w-full flex-none"
          label={label}
          helpText=""
          icon={<Tags />}
        >
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <TextField.Input placeholder={placeholder} />
              </Tooltip.Trigger>
              <Tooltip.Content
                side="bottom"
                align="center"
                sideOffset={4}
              >
                Separate multiple tags with a semicolon. e.g. tag1; tag2
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        </TextField>
        {tags ? (
          <div className="flex w-full flex-col items-start gap-4">{tags}</div>
        ) : null}
      </div>
    );
  }
);

export const TagInput = TagInputRoot;
