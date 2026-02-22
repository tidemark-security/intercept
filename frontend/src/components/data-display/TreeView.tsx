"use client";

import React from "react";


import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { Accordion } from "@/components/misc/Accordion";

import { File, Folder as FolderIcon } from 'lucide-react';
interface FolderProps extends React.ComponentProps<typeof Accordion> {
  children?: React.ReactNode;
  label?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

const Folder = React.forwardRef<
  React.ElementRef<typeof Accordion>,
  FolderProps
>(function Folder(
  {
    children,
    label,
    icon = <FolderIcon />,
    className,
    ...otherProps
  }: FolderProps,
  ref
) {
  return (
    <Accordion
      className={cn(
        "group/c841484c cursor-pointer",
        className
      )}
      trigger={
        <div className="flex w-full items-center gap-2 rounded-md px-3 py-2 group-hover/c841484c:bg-neutral-50">
          {icon ? (
            <IconWrapper className="text-body font-body text-default-font">
              {icon}
            </IconWrapper>
          ) : null}
          {label ? (
            <span className="line-clamp-1 grow shrink-0 basis-0 text-body font-body text-default-font">
              {label}
            </span>
          ) : null}
          <Accordion.Chevron />
        </div>
      }
      defaultOpen={true}
      ref={ref}
      {...otherProps}
    >
      {children ? (
        <div className="flex w-full flex-col items-start gap-1 pl-6 pt-1">
          {children}
        </div>
      ) : null}
    </Accordion>
  );
});

interface ItemProps extends React.HTMLAttributes<HTMLDivElement> {
  selected?: boolean;
  label?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

const Item = React.forwardRef<HTMLDivElement, ItemProps>(function Item(
  {
    selected = false,
    label,
    icon = <File />,
    className,
    ...otherProps
  }: ItemProps,
  ref
) {
  return (
    <div
      className={cn(
        "group/42786044 flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 hover:bg-neutral-50",
        { "bg-brand-100 hover:bg-brand-100": selected },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {icon ? (
        <IconWrapper
          className={cn(
            "text-body font-body text-default-font",
            { "text-brand-700": selected }
          )}
        >
          {icon}
        </IconWrapper>
      ) : null}
      {label ? (
        <span
          className={cn(
            "line-clamp-1 grow shrink-0 basis-0 text-body font-body text-default-font",
            { "text-brand-700": selected }
          )}
        >
          {label}
        </span>
      ) : null}
    </div>
  );
});

interface TreeViewRootProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

const TreeViewRoot = React.forwardRef<HTMLDivElement, TreeViewRootProps>(
  function TreeViewRoot(
    { children, className, ...otherProps }: TreeViewRootProps,
    ref
  ) {
    return children ? (
      <div
        className={cn(
          "flex w-full flex-col items-start",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {children}
      </div>
    ) : null;
  }
);

export const TreeView = Object.assign(TreeViewRoot, {
  Folder,
  Item,
});
