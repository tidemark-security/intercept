"use client";

import React, { Fragment, useState, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import Logo from "@/assets/TMS-logo-green.svg?react";

import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { SidebarRailWithLabels } from "@/components/navigation/SidebarRailWithLabels";
import { GlobalSearch } from "@/components/search/GlobalSearch";
import { OPEN_GLOBAL_SEARCH_EVENT, type OpenGlobalSearchDetail } from "@/components/search/globalSearchEvents";
import { useSession } from "@/contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { useSidebarBadgeCounts } from "@/hooks/useDashboard";
import { preloadRoute } from "@/routes/routePages";
import { alertFilterHref } from "@/utils/savedQueueFilters";
import { getIconComponent } from "@/utils/iconMapping";
import { cn } from "@/utils/cn";
import type { SidebarBadgeCount } from "@/types/generated/models/SidebarBadgeCount";
import { IconWrapper, ToggleGroup, Tooltip } from "@tidemark-security/ux";

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
  to: string;
  match: (path: string) => boolean;
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

type SidebarItemProps = {
  label: string;
  icon: React.ReactNode;
  mobile?: boolean;
  className?: string;
};

function sidebarItemClassName(mobile?: boolean, className?: string) {
  return cn(
    "group relative flex h-12 w-full items-center justify-center rounded-md p-2 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-border",
    mobile && "w-12 p-1",
    className,
  );
}

function SidebarItemIcon({ icon, selected }: { icon: React.ReactNode; selected?: boolean }) {
  return (
    <IconWrapper
      aria-hidden="true"
      className={cn(
        "text-heading-2 font-heading-2",
        selected ? "text-accent-1-400" : "text-brand-primary group-hover:text-brand-200 group-active:text-brand-200",
      )}
    >
      {icon}
    </IconWrapper>
  );
}

function SidebarItemTooltip({ label, mobile, children }: {
  label: React.ReactNode;
  mobile?: boolean;
  children: React.ReactElement;
}) {
  return (
    <Tooltip.Provider>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
        <Tooltip.Content side={mobile ? "top" : "right"} align="center" sideOffset={4} className="z-[9999]">
          <div className="text-caption font-caption text-black">{label}</div>
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

function routeIntentProps(to: string) {
  return {
    onFocus: () => { void preloadRoute(to); },
    onPointerEnter: (event: React.PointerEvent) => {
      if (event.pointerType !== "touch") void preloadRoute(to);
    },
  };
}

// The UX rail's NavItem renders a div. Use a router link as the tooltip trigger
// so keyboard, context-menu and modified clicks get native link behavior.
function SidebarLink({
  label,
  icon,
  to,
  selected,
  mobile,
  className,
  children,
}: SidebarItemProps & { to: string; selected?: boolean; children?: React.ReactNode }) {
  return (
    <SidebarItemTooltip label={children ?? label} mobile={mobile}>
      <Link
        to={to}
        viewTransition
        aria-label={label}
        aria-current={selected ? "page" : undefined}
        className={sidebarItemClassName(mobile, className)}
        {...routeIntentProps(to.split("?")[0])}
      >
        <SidebarItemIcon icon={icon} selected={selected} />
      </Link>
    </SidebarItemTooltip>
  );
}

const SidebarMenuButton = React.forwardRef<
  HTMLButtonElement,
  SidebarItemProps & React.ButtonHTMLAttributes<HTMLButtonElement>
>(function SidebarMenuButton({ label, icon, mobile, className, ...props }, ref) {
  return (
    <SidebarItemTooltip label={label} mobile={mobile}>
      <button
        ref={ref}
        type="button"
        aria-label={label}
        className={sidebarItemClassName(mobile, className)}
        {...props}
      >
        <SidebarItemIcon icon={icon} />
      </button>
    </SidebarItemTooltip>
  );
});

function formatBadgeCount(count: number) {
  return count > 99 ? "99+" : count.toString();
}

type SidebarBadgeGroupProps = {
  counts?: SidebarBadgeCount;
};

function SidebarNotificationBadge({ counts }: SidebarBadgeGroupProps) {
  if (!counts || counts.unassigned <= 0) {
    return null;
  }

  return (
    <span
      className="absolute right-0 top-0 inline-flex h-4 min-w-4 items-center justify-center border border-black bg-accent-2-primary px-1 text-[10px] font-monospace-body leading-none text-white"
      aria-hidden="true"
    >
      {formatBadgeCount(counts.unassigned)}
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
    ? `${label}: ${counts.unassigned} unassigned`
    : label;

  return (
    <span className="flex min-w-0 flex-1 items-center gap-2">
      <span className="truncate">{label}</span>
      {counts ? <span className="sr-only">{describedBy}</span> : null}
    </span>
  );
}

function SidebarQueueLinks({ mobile = false }: { mobile?: boolean }) {
  const { pathname, search } = useLocation();
  const { isAdmin } = useSession();
  const { data: sidebarBadgeCounts } = useSidebarBadgeCounts();
  const items = navigationItems.filter((item) => item.key !== "admin" || (isAdmin && !mobile));

  const pinned = sidebarBadgeCounts?.pinned_alert_filters ?? [];
  const pinId = new URLSearchParams(search).get("saved_filter");
  const activePin = pathname === "/alerts" || pathname.startsWith("/alerts/")
    ? pinned.find(({ filter }) => filter.id === pinId)
    : undefined;

  return items.map((item) => {
    const Icon = item.icon;
    const counts = item.badgeKey ? sidebarBadgeCounts?.[item.badgeKey] : undefined;
    return (
      <Fragment key={item.key}>
        <SidebarLink
          label={item.label}
          to={item.to}
          className={mobile ? item.mobileClassName : undefined}
          icon={<SidebarIconWithBadge icon={<Icon />} counts={counts} />}
          selected={item.match(pathname) && !(item.key === "alerts" && activePin)}
          mobile={mobile}
        >
          <SidebarNavLabel label={item.label} counts={counts} />
        </SidebarLink>
        {item.key === "alerts" && pinned.map(({ filter, counts }) => filter.navigation_icon && (
          <SidebarLink
            key={filter.id}
            label={filter.name}
            to={alertFilterHref(filter)}
            className={mobile ? "shrink-0" : undefined}
            icon={<SidebarIconWithBadge icon={getIconComponent(filter.navigation_icon)} counts={counts} />}
            selected={activePin?.filter.id === filter.id}
            mobile={mobile}
          >
            <SidebarNavLabel label={filter.name} counts={counts} />
          </SidebarLink>
        ))}
      </Fragment>
    );
  });
}

export function DesktopSidebar() {
  const { pathname } = useLocation();
  const { timezonePreference, setTimezonePreference } = useTimezonePreference();
  const { resolvedTheme, setThemePreference } = useTheme();
  const timezoneLabel = `Timezone (${timezonePreference === "utc" ? "UTC" : "Local"})`;

  return (
    <SidebarRailWithLabels
      className="mobile:hidden"
      header={
        <>
          <Link
            to="/"
            viewTransition
            aria-label="Tidemark home"
            className="block flex-none focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-border"
            {...routeIntentProps("/")}
          >
            <Logo width="64" height="64" aria-hidden="true" focusable="false" />
          </Link>
          <SidebarLink
            label="Search"
            icon={<Search />}
            to="/search"
            selected={pathname === "/search"}
          />
        </>
      }
      footer={
        <>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <SidebarMenuButton
                label={timezoneLabel}
                icon={<Clock />}
              />
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
          <SidebarLink
            label="Profile"
            icon={<User />}
            to="/profile"
            selected={pathname === "/profile"}
          />
          <SidebarLink
            label="Logout"
            icon={<Lock />}
            to="/logout"
          />
        </>
      }
    >
      <SidebarQueueLinks />
    </SidebarRailWithLabels>
  );
}

export function MobileSidebar() {
  const { isAdmin } = useSession();

  return (
    <SidebarRailWithLabels
      className="hidden mobile:flex mobile:flex-none mobile:z-50"
      mobile={true}
    >
      <SidebarQueueLinks mobile />
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <SidebarMenuButton label="More navigation" icon={<Menu />} mobile />
        </DropdownMenu.Trigger>
        <DropdownMenu.Content side="bottom" align="start" sideOffset={4}>
          <DropdownMenu.DropdownItem icon={<Search />} label="Search" to="/search" {...routeIntentProps("/search")} />
          {isAdmin ? (
            <>
              <DropdownMenu.DropdownItem
                icon={<Settings />}
                hint=""
                label="Admin"
                to="/admin"
                {...routeIntentProps("/admin")}
              />
              <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
            </>
          ) : null}
          <DropdownMenu.DropdownItem
            icon={<User />}
            hint=""
            label="Profile"
            to="/profile"
            {...routeIntentProps("/profile")}
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
