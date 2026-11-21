"use client";

import React from "react";
import { DefaultPageLayout as UxDefaultPageLayout } from "@tidemark-security/ux";
import type { DefaultPageLayoutProps as UxDefaultPageLayoutProps } from "@tidemark-security/ux";
import { DesktopSidebar, MobileSidebar, SearchOverlay } from "./AppSidebar";
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
      className={cn(styles.priorityBackdrop, className)}
      desktopSidebar={<DesktopSidebar />}
      mobileSidebar={<MobileSidebar />}
      overlaySlot={<SearchOverlay />}
      {...props}
    />
  );
});

export const DefaultPageLayout = DefaultPageLayoutRoot;
