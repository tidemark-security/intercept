import React from "react";
import { Link } from "@/components/navigation/Link";
import { IconButton } from "@/components/buttons/IconButton";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";


import { ArrowLeft } from 'lucide-react';
interface AdminPageLayoutProps {
  /** Page title */
  title: string;
  /** Page subtitle/description */
  subtitle?: string;
  /** Action button to display in top-right (e.g., Add button) */
  actionButton?: React.ReactNode;
  /** Page content */
  children: React.ReactNode;
}

/**
 * Layout component for admin pages
 * 
 * Provides consistent header with back button to /admin, title/subtitle,
 * and optional action button. Content area has max-width-7xl for efficient
 * screen space usage. Includes border effect and top-right corner clipping
 * matching the admin dashboard styling.
 */
export const AdminPageLayout: React.FC<AdminPageLayoutProps> = ({
  title,
  subtitle,
  actionButton,
  children,
}) => {
  return (
    <DefaultPageLayout withContainer>
      <div className="flex h-full w-full flex-col items-start gap-6 overflow-auto px-6 py-12 mobile:px-4 mobile:py-6">
        <div className="mx-auto flex w-full max-w-7xl flex-col items-start gap-6">
          {/* Header */}
          <div className="flex w-full flex-shrink-0 items-center justify-between">
            <div className="flex items-center gap-4">
              <Link to="/admin">
                <IconButton icon={<ArrowLeft />} />
              </Link>
              <div className="flex flex-col items-start gap-1">
                <span className="text-heading-1 font-heading-1 text-default-font">
                  {title}
                </span>
                {subtitle && (
                  <span className="text-body font-body text-subtext-color">
                    {subtitle}
                  </span>
                )}
              </div>
            </div>
            {actionButton && <div>{actionButton}</div>}
          </div>

          {/* Content */}
          <div className="flex w-full flex-col items-start gap-6">
            {children}
          </div>
        </div>
      </div>
    </DefaultPageLayout>
  );
};
