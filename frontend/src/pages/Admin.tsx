import React from "react";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";

import { useSession } from "../contexts/sessionContext";
import { DashboardCard } from "@/components/cards/DashboardCard";

import { AlertCircle, Link2, Settings, Users } from 'lucide-react';
interface AdminCard {
  title: string;
  description: string;
  icon: React.ReactNode;
  link: string;
}

const adminCards: AdminCard[] = [
  {
    title: "User Management",
    description: "Manage users, roles, and account status",
    icon: <Users />,
    link: "/admin/users",
  },
  {
    title: "Link Templates",
    description: "Configure contextual action links for timeline items",
    icon: <Link2 />,
    link: "/admin/link-templates",
  },
  {
    title: "Configuration Settings",
    description: "Configure advanced system settings and preferences",
    icon: <Settings />,
    link: "/admin/settings",
  },
];

function Admin() {
  const { user: currentUser } = useSession();
  const isAdmin = currentUser?.role === "ADMIN";

  if (!isAdmin) {
    return (
      <DefaultPageLayout withContainer>
        <div className="container max-w-none flex h-full w-full flex-col items-center justify-center gap-4">
          <AlertCircle className="text-[48px] text-error text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">
            Access Denied
          </span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to access administration
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  return (
    <DefaultPageLayout withContainer>
      <div className="container max-w-none flex h-full w-full flex-col items-start gap-6 py-12">
        {/* Header */}
        <div className="flex w-full flex-col items-start gap-2">
          <div className="flex items-center gap-3">
            <Settings className="text-[32px] text-brand-primary" />
            <span className="text-heading-1 font-heading-1 text-default-font">
              Administration
            </span>
          </div>
          <span className="text-body font-body text-subtext-color">
            Manage system settings, users, and configurations
          </span>
        </div>

        {/* Admin Cards Grid */}
        <div className="grid w-full grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {adminCards.map((card) => (
            <DashboardCard
              key={card.link}
              title={card.title}
              description={card.description}
              icon={card.icon}
              link={card.link}
            />
          ))}
        </div>
      </div>
    </DefaultPageLayout>
  );
}

export default Admin;
