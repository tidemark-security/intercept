import React from "react";
import { AdminPageLayout as UxAdminPageLayout } from "@tidemark-security/ux";
import type { AdminPageLayoutProps } from "@tidemark-security/ux";
import { DesktopSidebar, MobileSidebar, SearchOverlay } from "./AppSidebar";

export type { AdminPageLayoutProps };

export const AdminPageLayout: React.FC<AdminPageLayoutProps> = (props) => {
  return (
    <UxAdminPageLayout
      {...props}
      layoutProps={{
        ...props.layoutProps,
        desktopSidebar: <DesktopSidebar />,
        mobileSidebar: <MobileSidebar />,
        overlaySlot: <SearchOverlay />,
      }}
    />
  );
};
