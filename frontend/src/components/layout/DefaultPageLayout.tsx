"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useViewTransitionNavigate } from "@/hooks/useViewTransitionNavigate";
import Logo from "@/assets/TMS-logo-green.svg?react";

import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { ToggleGroup } from "@/components/buttons/ToggleGroup";
import { SidebarRailWithLabels } from "@/components/navigation/SidebarRailWithLabels";
import { GlobalSearch } from "@/components/search/GlobalSearch";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { cn } from "@/utils/cn";

import {
  BarChart2,
  Bell,
  Clock,
  Globe,
  Home,
  List,
  Lock,
  MapPin,
  Menu,
  MessageCircle,
  NotebookPen,
  Search,
  Settings,
  User,
} from "lucide-react";
type NavigationItem = {
  key: string;
  label: string;
  icon: React.ComponentType;
  to?: string;
  match?: (path: string) => boolean;
  mobileClassName?: string;
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
  },
  {
    key: "cases",
    label: "Cases",
    icon: NotebookPen,
    to: "/cases",
    match: (path: string) => path.startsWith("/cases"),
  },
  {
    key: "tasks",
    label: "Tasks",
    icon: List,
    to: "/tasks",
    match: (path: string) => path.startsWith("/tasks"),
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
    key: "admin",
    label: "Admin",
    icon: Settings,
    to: "/admin",
    match: (path: string) => path.startsWith("/admin"),
  },
];

interface DefaultPageLayoutRootProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
  // Accepts both API (UPPERCASE) and UI (lowercase) priority values
  priority?:
    | "info"
    | "low"
    | "medium"
    | "high"
    | "critical"
    | "extreme"
    | "INFO"
    | "LOW"
    | "MEDIUM"
    | "HIGH"
    | "CRITICAL"
    | "EXTREME";
  withContainer?: boolean;
}

const DefaultPageLayoutRoot = React.forwardRef<
  HTMLDivElement,
  DefaultPageLayoutRootProps
>(function DefaultPageLayoutRoot(
  {
    children,
    className,
    priority,
    withContainer,
    ...otherProps
  }: DefaultPageLayoutRootProps,
  ref,
) {
  const location = useLocation();
  const navigate = useViewTransitionNavigate();
  const { timezonePreference, setTimezonePreference } = useTimezonePreference();
  const mobileNavItems = navigationItems.filter((item) => item.key !== "admin");

  // Global search state
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  // Cmd+K / Ctrl+K keyboard shortcut to open search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Check for Cmd+K (Mac) or Ctrl+K (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsSearchOpen(true);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const isItemSelected = React.useCallback(
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

  const handleNavClick = React.useCallback(
    (item: NavigationItem) => {
      if (!item.to) {
        return;
      }
      navigate(item.to);
    },
    [navigate],
  );

  const handleNavKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>, item: NavigationItem) => {
      if (!item.to) {
        return;
      }
      if (event.key === "Enter" || event.key === " " || event.key === "Space") {
        event.preventDefault();
        navigate(item.to);
      }
    },
    [navigate],
  );

  const getPriorityClasses = () => {
    // Normalize priority to lowercase to handle both API (UPPERCASE) and UI (lowercase) values
    const normalizedPriority = priority?.toLowerCase();
    switch (normalizedPriority) {
      case "extreme":
        return {
          gradient: "bg-p0/60",
        };
      case "critical":
        return {
          gradient: "bg-p1",
        };
      case "high":
        return {
          gradient: "bg-p2/60",
        };
      case "medium":
        return {
          gradient: "bg-p3/60",
        };
      case "low":
        return {
          gradient: "bg-p4/60",
        };
      case "info":
        return {
          gradient: "bg-p5/50",
        };
      default:
        return {
          gradient: "bg-transparent",
        };
    }
  };

  const { gradient } = getPriorityClasses();

  return (
    <div
      className={cn(
        "flex h-screen w-full items-center justify-center bg-p0 mobile:flex-col mobile:flex-nowrap mobile:items-end mobile:justify-center mobile:gap-0",
        className,
      )}
      ref={ref}
      {...otherProps}
    >
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
            <SidebarRailWithLabels.NavItem
              icon={<Search />}
              onClick={() => navigate("/search")}
              selected={
                location.pathname === "/search" ||
                location.pathname.startsWith("/search?")
              }
              aria-label="Search"
              title="Search"
            >
              Search
            </SidebarRailWithLabels.NavItem>
          </>
        }
        footer={
          <>
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <SidebarRailWithLabels.NavItem
                  icon={<Clock />}
                  title="Timezone"
                >
                  Timezone ({timezonePreference === "utc" ? "UTC" : "Local"})
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
                </div>
              </DropdownMenu.Content>
            </DropdownMenu.Root>
            <SidebarRailWithLabels.NavItem
              icon={<User />}
              onClick={() => navigate("/profile")}
            >
              Profile
            </SidebarRailWithLabels.NavItem>
            <SidebarRailWithLabels.NavItem
              icon={<Lock />}
              onClick={() => navigate("/logout")}
            >
              Logout
            </SidebarRailWithLabels.NavItem>
          </>
        }
      >
        {navigationItems.map((item) => {
          const Icon = item.icon;
          const selected = isItemSelected(item);
          return (
            <SidebarRailWithLabels.NavItem
              key={item.key}
              icon={<Icon />}
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
              {item.label}
            </SidebarRailWithLabels.NavItem>
          );
        })}
      </SidebarRailWithLabels>
      {children ? (
        <div
          className={cn(
            "relative flex grow shrink-0 basis-0 flex-col items-start self-stretch overflow-hidden bg-page-background transition-all duration-500",
          )}
        >
          <div
            className="absolute inset-0 z-0 pointer-events-none"
            style={{
              maskImage: "linear-gradient(0deg, black, transparent 45%)",
              WebkitMaskImage: "linear-gradient(0deg, black, transparent 65%)",
            }}
          >
            <div
              className={cn(
                "absolute inset-0 transition-colors duration-500 mobile:bg-transparent",
                gradient,
              )}
              style={{
                maskImage:
                  "repeating-linear-gradient(135deg, transparent, transparent 20px, black 20px, black 40px)",
                WebkitMaskImage:
                  "repeating-linear-gradient(135deg, transparent, transparent 20px, black 20px, black 40px)",
              }}
            />
          </div>
          <div
            className={cn(
              "relative z-10 flex h-full w-full flex-col items-start gap-4 overflow-y-auto",
              { "p-4 mobile:p-0": !!withContainer },
            )}
          >
            {withContainer ? (
              <div className="flex flex-1 w-full flex-col items-start bg-default-background bevel-tr-3xl">
                {children}
              </div>
            ) : (
              children
            )}
          </div>
        </div>
      ) : null}
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
          return (
            <SidebarRailWithLabels.NavItem
              key={item.key}
              className={item.mobileClassName}
              icon={<Icon />}
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
              {item.label}
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
            <DropdownMenu.DropdownItem
              icon={<Settings />}
              hint=""
              label="Admin"
              to="/admin"
            />
            <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
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

      {/* Global Search Dialog */}
      <GlobalSearch open={isSearchOpen} onOpenChange={setIsSearchOpen} />
    </div>
  );
});

export const DefaultPageLayout = DefaultPageLayoutRoot;
