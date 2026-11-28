"use client";

import React from "react";
import { DefaultPageLayout as UxDefaultPageLayout } from "@tidemark-security/ux";
import type { DefaultPageLayoutProps as UxDefaultPageLayoutProps } from "@tidemark-security/ux";
import { cn } from "@/utils/cn";
import styles from "./DefaultPageLayout.module.css";

interface DefaultPageLayoutProps extends Omit<UxDefaultPageLayoutProps, "desktopSidebar" | "mobileSidebar" | "overlaySlot"> {
  children?: React.ReactNode;
}

const DefaultPageLayoutRoot = React.forwardRef<
  HTMLDivElement,
  DefaultPageLayoutProps
>(function DefaultPageLayoutRoot({ className, ...props }, ref) {
  return (
    <UxDefaultPageLayout
      ref={ref}
      className={cn("h-full min-h-0", styles.priorityBackdrop, className)}
      {...props}
    />
  );
});

export const DefaultPageLayout = DefaultPageLayoutRoot;
