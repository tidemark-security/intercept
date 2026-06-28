"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useViewTransitionNavigate } from "@/hooks/useViewTransitionNavigate";
import Logo from "@/assets/TMS-logo-green.svg?react";

import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { SidebarRailWithLabels } from "@/components/navigation/SidebarRailWithLabels";
import { GlobalSearch } from "@/components/search/GlobalSearch";
import { OPEN_GLOBAL_SEARCH_EVENT, type OpenGlobalSearchDetail } from "@/components/search/globalSearchEvents";
import { useSession } from "@/contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { useSidebarBadgeCounts } from "@/hooks/useDashboard";
import { cn } from "@/utils/cn";
import type { SidebarBadgeCount } from "@/types/generated/models/SidebarBadgeCount";
import { ToggleGroup } from "@tidemark-security/ux";

import {
  BarChart2,
  Bell,
  BrainCircuit,
  CheckSquare,
  Clock,
  Globe,
  Home,
  Lock,
  MapPin,
  Menu,
  MessageCircle,
  Moon,
  NotebookPen,
  Search,
  Settings,
  SportShoe,
  Sun,
  User,
} from "lucide-react";

type NavigationItem = {
  key: string;
  label: string;
  icon: React.ComponentType;
  to?: string;
  match?: (path: string) => boolean;
  mobileClassName?: string;
  badgeKey?: "alerts" | "cases" | "tasks";
};

const navigationItems: NavigationItem[] = [
  {
    key: "home",
    label: "Home",
    icon: Home,
    to: "/",
    match: (path: string) => path === "/",
    mobileClassName: "h-auto min-h-[48px] w-12 flex-none",
  },
  {
    key: "alerts",
    label: "Alerts",
    icon: Bell,
    to: "/alerts",
    match: (path: string) => path === "/alerts" || path.startsWith("/alerts/"),
    badgeKey: "alerts",
  },
  {
    key: "cases",
    label: "Cases",
    icon: NotebookPen,
    to: "/cases",
    match: (path: string) => path.startsWith("/cases"),
    badgeKey: "cases",
  },
  {
    key: "tasks",
    label: "Tasks",
    icon: CheckSquare,
    to: "/tasks",
    match: (path: string) => path.startsWith("/tasks"),
    badgeKey: "tasks",
  },
  {
    key: "ai-chat",
    label: "AI Chat",
    icon: MessageCircle,
    to: "/ai-chat",
    match: (path: string) => path.startsWith("/ai-chat"),
  },
  {
    key: "reports",
    label: "Reports",
    icon: BarChart2,
    to: "/reports",
    match: (path: string) => path.startsWith("/reports"),
  },
  {
    key: "context-entries",
    label: "Context",
    icon: BrainCircuit,
    to: "/context-entries",
    match: (path: string) => path.startsWith("/context-entries"),
  },
  {
    key: "case-runbooks",
    label: "Runbooks",
    icon: SportShoe,
    to: "/case-runbooks",
    match: (path: string) => path.startsWith("/case-runbooks"),
  },
  {
    key: "admin",
    label: "Admin",
    icon: Settings,
    to: "/admin",
    match: (path: string) => path.startsWith("/admin"),
  },
];

type SidebarNavItemProps = React.ComponentProps<
  typeof SidebarRailWithLabels.NavItem
> & {
  label: string;
};

function SidebarNavItem({
  label,
  children,
  ...navItemProps
}: SidebarNavItemProps) {
  return (
    <SidebarRailWithLabels.NavItem aria-label={label} {...navItemProps}>
      {children}
    </SidebarRailWithLabels.NavItem>
  );
}

function formatBadgeCount(count: number) {
  return count > 99 ? "99+" : count.toString();
}

type SidebarBadgeGroupProps = {
  counts?: SidebarBadgeCount;
};

function SidebarNotificationBadge({ counts }: SidebarBadgeGroupProps) {
  if (!counts || counts.open <= 0) {
    return null;
  }

  return (
    <span
      className="absolute right-0 top-0 inline-flex h-4 min-w-4 items-center justify-center border border-black bg-accent-2-primary px-1 text-[10px] font-monospace-body leading-none text-white"
      aria-hidden="true"
    >
      {formatBadgeCount(counts.open)}
    </span>
  );
}

type SidebarIconWithBadgeProps = {
  icon: React.ReactNode;
  counts?: SidebarBadgeCount;
};

function SidebarIconWithBadge({ icon, counts }: SidebarIconWithBadgeProps) {
  return (
    <span className="inline-flex">
      {icon}
      <SidebarNotificationBadge counts={counts} />
    </span>
  );
}

type SidebarNavLabelProps = {
  label: string;
  counts?: SidebarBadgeCount;
};

function SidebarNavLabel({ label, counts }: SidebarNavLabelProps) {
  const describedBy = counts
    ? `${label}: ${counts.open} open`
    : label;

  return (
    <span className="flex min-w-0 flex-1 items-center gap-2">
      <span className="truncate">{label}</span>
      {counts ? <span className="sr-only">{describedBy}</span> : null}
    </span>
  );
}

function useNavigation() {
  const location = useLocation();
  const navigate = useViewTransitionNavigate();
  const { isAdmin } = useSession();

  const visibleNavigationItems = isAdmin
    ? navigationItems
    : navigationItems.filter((item) => item.key !== "admin");
  const mobileNavItems = navigationItems.filter((item) => item.key !== "admin");

  const isItemSelected = useCallback(
    (item: NavigationItem) => {
      if (item.match) {
        return item.match(location.pathname);
      }
      if (!item.to) {
        return false;
      }
      return location.pathname === item.to;
    },
    [location.pathname],
  );

  const handleNavClick = useCallback(
    (itemOrPath: NavigationItem | string) => {
      const path = typeof itemOrPath === 'string' ? itemOrPath : itemOrPath.to;
      if (!path) return;
      navigate(path);
    },
    [navigate],
  );

  const handleNavKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>, itemOrPath: NavigationItem | string) => {
      const path = typeof itemOrPath === 'string' ? itemOrPath : itemOrPath.to;
      if (!path) return;
      if (event.key === "Enter" || event.key === " " || event.key === "Space") {
        event.preventDefault();
        navigate(path);
      }
    },
    [navigate],
  );

  return {
    location,
    isAdmin,
    visibleNavigationItems,
    mobileNavItems,
    isItemSelected,
    handleNavClick,
    handleNavKeyDown,
  };
}

export function DesktopSidebar() {
  const {
    location,
    visibleNavigationItems,
    isItemSelected,
    handleNavClick,
    handleNavKeyDown,
  } = useNavigation();
  const { data: sidebarBadgeCounts } = useSidebarBadgeCounts();
  const { timezonePreference, setTimezonePreference } = useTimezonePreference();
  const { resolvedTheme, setThemePreference } = useTheme();
  const timezoneLabel = `Timezone (${timezonePreference === "utc" ? "UTC" : "Local"})`;

  return (
    <SidebarRailWithLabels
      className="mobile:hidden"
      header={
        <>
          <Logo
            className="flex-none"
            width="64"
            height="64"
            aria-label="TMS Logo"
          />
          <SidebarNavItem
            label="Search"
            icon={<Search />}
            role="button"
            tabIndex={0}
            onClick={() => handleNavClick("/search")}
            onKeyDown={(event: React.KeyboardEvent<HTMLDivElement>) =>
              handleNavKeyDown(event, "/search")
            }
            selected={
              location.pathname === "/search" ||
              location.pathname.startsWith("/search?")
            }
          >
            Search
          </SidebarNavItem>
        </>
      }
      footer={
        <>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <SidebarRailWithLabels.NavItem
                aria-label={timezoneLabel}
                icon={<Clock />}
                role="button"
                tabIndex={0}
              >
                {timezoneLabel}
              </SidebarRailWithLabels.NavItem>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content side="right" align="end" sideOffset={8}>
              <div className="flex max-w-[256px] flex-col gap-3 px-2 py-2">
                <span className="text-caption-bold font-caption-bold text-default-font">
                  Display Timezone
                </span>
                <ToggleGroup
                  type="single"
                  value={timezonePreference}
                  onValueChange={(value) => {
                    if (value === "utc" || value === "local") {
                      setTimezonePreference(value);
                    }
                  }}
                  className="w-full justify-start"
                >
                  <ToggleGroup.Item
                    value="local"
                    icon={<MapPin />}
                    className="flex-1 justify-center"
                  >
                    Local
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    value="utc"
                    icon={<Globe />}
                    className="flex-1 justify-center"
                  >
                    UTC
                  </ToggleGroup.Item>
                </ToggleGroup>
                <span className="text-caption text-default-font">
                  Datetime inputs are always in your local timezone regardless of this setting.
                </span>
                <div className="h-px w-full bg-neutral-border" />
                <span className="text-caption-bold font-caption-bold text-default-font">
                  Display Theme
                </span>
                <ToggleGroup
                  type="single"
                  value={resolvedTheme}
                  onValueChange={(value) => {
                    if (value === "dark" || value === "light") {
                      setThemePreference(value);
                    }
                  }}
                  className="w-full justify-start"
                >
                  <ToggleGroup.Item
                    value="light"
                    icon={<Sun />}
                    className="flex-1 justify-center"
                  >
                    Light
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    value="dark"
                    icon={<Moon />}
                    className="flex-1 justify-center"
                  >
                    Dark
                  </ToggleGroup.Item>
                </ToggleGroup>
              </div>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
          <SidebarNavItem
            label="Profile"
            icon={<User />}
            role="button"
            tabIndex={0}
            onClick={() => handleNavClick("/profile")}
            onKeyDown={(event: React.KeyboardEvent<HTMLDivElement>) =>
              handleNavKeyDown(event, "/profile")
            }
          >
            Profile
          </SidebarNavItem>
          <SidebarNavItem
            label="Logout"
            icon={<Lock />}
            role="button"
            tabIndex={0}
            onClick={() => handleNavClick("/logout")}
            onKeyDown={(event: React.KeyboardEvent<HTMLDivElement>) =>
              handleNavKeyDown(event, "/logout")
            }
          >
            Logout
          </SidebarNavItem>
        </>
      }
    >
      {visibleNavigationItems.map((item) => {
        const Icon = item.icon;
        const selected = isItemSelected(item);
        const counts = item.badgeKey ? sidebarBadgeCounts?.[item.badgeKey] : undefined;
        return (
          <SidebarNavItem
            key={item.key}
            label={item.label}
            className="relative"
            icon={<SidebarIconWithBadge icon={<Icon />} counts={counts} />}
            selected={selected}
            aria-current={selected ? "page" : undefined}
            role={item.to ? "button" : undefined}
            tabIndex={item.to ? 0 : undefined}
            onClick={item.to ? () => handleNavClick(item) : undefined}
            onKeyDown={
              item.to
                ? (event: React.KeyboardEvent<HTMLDivElement>) =>
                  handleNavKeyDown(event, item)
                : undefined
            }
          >
            <SidebarNavLabel label={item.label} counts={counts} />
          </SidebarNavItem>
        );
      })}
    </SidebarRailWithLabels>
  );
}

export function MobileSidebar() {
  const {
    isAdmin,
    mobileNavItems,
    isItemSelected,
    handleNavClick,
    handleNavKeyDown,
  } = useNavigation();
  const { data: sidebarBadgeCounts } = useSidebarBadgeCounts();

  return (
    <SidebarRailWithLabels
      className="hidden mobile:flex mobile:flex-none mobile:z-50"
      header={
        <div className="flex flex-col items-center justify-center gap-2"></div>
      }
      footer={
        <>
          <SidebarRailWithLabels.NavItem mobile={true} />
          <SidebarRailWithLabels.NavItem mobile={true} />
        </>
      }
      mobile={true}
    >
      {mobileNavItems.map((item) => {
        const Icon = item.icon;
        const selected = isItemSelected(item);
        const counts = item.badgeKey ? sidebarBadgeCounts?.[item.badgeKey] : undefined;
        return (
          <SidebarRailWithLabels.NavItem
            key={item.key}
            className={cn(item.mobileClassName, "relative")}
            icon={<SidebarIconWithBadge icon={<Icon />} counts={counts} />}
            selected={selected}
            mobile={true}
            aria-current={selected ? "page" : undefined}
            role={item.to ? "button" : undefined}
            tabIndex={item.to ? 0 : undefined}
            onClick={item.to ? () => handleNavClick(item) : undefined}
            onKeyDown={
              item.to
                ? (event: React.KeyboardEvent<HTMLDivElement>) =>
                  handleNavKeyDown(event, item)
                : undefined
            }
          >
            <SidebarNavLabel label={item.label} counts={counts} />
          </SidebarRailWithLabels.NavItem>
        );
      })}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <SidebarRailWithLabels.NavItem icon={<Menu />} mobile={true}>
            Item
          </SidebarRailWithLabels.NavItem>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content side="bottom" align="start" sideOffset={4}>
          {isAdmin ? (
            <>
              <DropdownMenu.DropdownItem
                icon={<Settings />}
                hint=""
                label="Admin"
                to="/admin"
              />
              <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
            </>
          ) : null}
          <DropdownMenu.DropdownItem
            icon={<User />}
            hint=""
            label="Profile"
            to="/profile"
          />
          <DropdownMenu.DropdownItem
            icon={<Lock />}
            hint="s"
            label="Logout"
            to="/logout"
          />
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    </SidebarRailWithLabels>
  );
}

export function SearchOverlay() {
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [initialTags, setInitialTags] = useState<string[]>([]);
  const [searchRequestKey, setSearchRequestKey] = useState(0);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsSearchOpen(true);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    const handleOpenSearch = (event: Event) => {
      const detail = (event as CustomEvent<OpenGlobalSearchDetail>).detail;

      setInitialTags(detail?.tags ?? []);
      setSearchRequestKey((current) => current + 1);
      setIsSearchOpen(true);
    };

    window.addEventListener(OPEN_GLOBAL_SEARCH_EVENT, handleOpenSearch);
    return () => window.removeEventListener(OPEN_GLOBAL_SEARCH_EVENT, handleOpenSearch);
  }, []);

  return (
    <GlobalSearch
      open={isSearchOpen}
      onOpenChange={setIsSearchOpen}
      initialTags={initialTags}
      searchRequestKey={searchRequestKey}
    />
  );
}
