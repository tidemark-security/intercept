"use client";

import React from "react";
import { DefaultPageLayout as UxDefaultPageLayout } from "@tidemark-security/ux";
import type { DefaultPageLayoutProps as UxDefaultPageLayoutProps } from "@tidemark-security/ux";
import { DesktopSidebar, MobileSidebar, SearchOverlay } from "./AppSidebar";

interface DefaultPageLayoutProps extends Omit<UxDefaultPageLayoutProps, "desktopSidebar" | "mobileSidebar" | "overlaySlot"> {
  children?: React.ReactNode;
}

const DefaultPageLayoutRoot = React.forwardRef<
  HTMLDivElement,
  DefaultPageLayoutProps
>(function DefaultPageLayoutRoot(props, ref) {
  return (
    <UxDefaultPageLayout
      ref={ref}
      desktopSidebar={<DesktopSidebar />}
      mobileSidebar={<MobileSidebar />}
      overlaySlot={<SearchOverlay />}
      {...props}
    />
  );
});

export const DefaultPageLayout = DefaultPageLayoutRoot;
