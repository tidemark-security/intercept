import React from "react";
import { ArrowLeft } from "lucide-react";
import { IconButton, Link } from "@tidemark-security/ux";
import type { AdminPageLayoutProps } from "@tidemark-security/ux";
import { DefaultPageLayout } from "./DefaultPageLayout";

export type { AdminPageLayoutProps };

export const AdminPageLayout: React.FC<AdminPageLayoutProps> = ({
  title,
  subtitle,
  actionButton,
  children,
  backTo = "/admin",
  backSlot,
  layoutProps,
}) => {
  return (
    <DefaultPageLayout withContainer {...layoutProps}>
      <div className="mx-auto flex h-full w-full max-w-[1536px] flex-col items-start gap-6 px-6 py-8 mobile:px-4">
        <div className="flex w-full flex-shrink-0 items-center justify-between">
          <div className="flex items-center gap-4">
            {backSlot ? (
              backSlot
            ) : (
              <Link to={backTo}>
                <IconButton icon={<ArrowLeft />} />
              </Link>
            )}
            <div className="flex flex-col items-start gap-1">
              <span className="text-heading-1 font-heading-1 text-default-font">{title}</span>
              {subtitle ? <span className="text-body font-body text-subtext-color">{subtitle}</span> : null}
            </div>
          </div>
          {actionButton ? <div>{actionButton}</div> : null}
        </div>
        <div className="flex w-full flex-col items-start gap-6">{children}</div>
      </div>
    </DefaultPageLayout>
  );
};
