import { fireEvent, render, screen, within } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DesktopSidebar } from "@/components/layout/AppSidebar";
import {
  SessionContext,
  sessionInitialState,
  type SessionContextValue,
} from "@/contexts/sessionContext";

const mockUseSidebarBadgeCounts = vi.hoisted(() => vi.fn());

vi.mock("@/assets/TMS-logo-green.svg?react", () => ({
  default: (props: React.SVGProps<SVGSVGElement>) => (
    <svg {...props} data-testid="tms-logo" />
  ),
}));

vi.mock("@/hooks/useDashboard", () => ({
  useSidebarBadgeCounts: mockUseSidebarBadgeCounts,
}));

vi.mock("@tidemark-security/ux", async () => {
  const React = await import("react");

  type TooltipContextValue = {
    open: boolean;
    setOpen: (open: boolean) => void;
  };

  const TooltipStateContext = React.createContext<TooltipContextValue | null>(
    null,
  );

  const composeEventHandlers =
    <EventType,>(
      first?: (event: EventType) => void,
      second?: (event: EventType) => void,
    ) =>
    (event: EventType) => {
      first?.(event);
      second?.(event);
    };

  function cloneWithProps(
    children: React.ReactNode,
    props: Record<string, unknown>,
  ) {
    if (!React.isValidElement(children)) {
      return children;
    }

    return React.cloneElement(
      children as React.ReactElement<Record<string, unknown>>,
      props,
    );
  }

  const Tooltip = {
    Provider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    Root: ({ children }: { children: React.ReactNode }) => {
      const [open, setOpen] = React.useState(false);
      return (
        <TooltipStateContext.Provider value={{ open, setOpen }}>
          {children}
        </TooltipStateContext.Provider>
      );
    },
    Trigger: ({
      children,
    }: {
      asChild?: boolean;
      children: React.ReactNode;
    }) => {
      const context = React.useContext(TooltipStateContext);
      const child = React.isValidElement(children)
        ? (children as React.ReactElement<{
            onFocus?: React.FocusEventHandler;
            onBlur?: React.FocusEventHandler;
            onMouseEnter?: React.MouseEventHandler;
            onMouseLeave?: React.MouseEventHandler;
          }>)
        : null;

      if (!context || !child) {
        return children;
      }

      return React.cloneElement(child, {
        onFocus: composeEventHandlers(child.props.onFocus, () =>
          context.setOpen(true),
        ),
        onBlur: composeEventHandlers(child.props.onBlur, () =>
          context.setOpen(false),
        ),
        onMouseEnter: composeEventHandlers(child.props.onMouseEnter, () =>
          context.setOpen(true),
        ),
        onMouseLeave: composeEventHandlers(child.props.onMouseLeave, () =>
          context.setOpen(false),
        ),
      });
    },
    Content: ({ children }: { children: React.ReactNode }) => {
      const context = React.useContext(TooltipStateContext);
      return context?.open ? <div role="tooltip">{children}</div> : null;
    },
  };

  const SidebarRailWithLabels = ({
    header,
    children,
    footer,
  }: {
    header?: React.ReactNode;
    children: React.ReactNode;
    footer?: React.ReactNode;
  }) => (
    <nav aria-label="Desktop sidebar">
      <div>{header}</div>
      <div>{children}</div>
      <div>{footer}</div>
    </nav>
  );

  const DropdownMenu = {
    Root: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    Trigger: ({
      children,
      ...props
    }: {
      asChild?: boolean;
      children: React.ReactNode;
    }) => cloneWithProps(children, props as Record<string, unknown>),
    Content: () => null,
    DropdownItem: () => null,
  };

  const ToggleGroup = Object.assign(
    ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    {
      Item: ({ children }: { children: React.ReactNode }) => (
        <button type="button">{children}</button>
      ),
    },
  );

  return {
    cn: (...classes: Array<string | false | null | undefined>) =>
      classes.filter(Boolean).join(" "),
    DropdownMenu,
    SidebarRailWithLabels,
    IconWrapper: (props: React.HTMLAttributes<HTMLSpanElement>) => <span {...props} />,
    ToggleGroup,
    Tooltip,
    useTheme: () => ({
      resolvedTheme: "light",
      setThemePreference: vi.fn(),
    }),
    useTimezonePreference: () => ({
      timezonePreference: "local",
      setTimezonePreference: vi.fn(),
    }),
  };
});

const sessionValue: SessionContextValue = {
  ...sessionInitialState,
  status: "authenticated",
  login: vi.fn(),
  loginWithPasskey: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
  resolveError: vi.fn(),
  acknowledgeLockout: vi.fn(),
  setMustChangePassword: vi.fn(),
  isAdmin: true,
  isAnalyst: false,
  isAuditor: false,
};

function renderDesktopSidebar() {
  return render(
    <SessionContext.Provider value={sessionValue}>
      <MemoryRouter>
        <DesktopSidebar />
      </MemoryRouter>
    </SessionContext.Provider>,
  );
}

describe("DesktopSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSidebarBadgeCounts.mockReturnValue({ data: undefined });
  });

  it("exposes each page destination as a single named native link", () => {
    renderDesktopSidebar();

    const destinations = {
      "Tidemark home": "/",
      Search: "/search",
      Home: "/",
      Alerts: "/alerts",
      Cases: "/cases",
      Tasks: "/tasks",
      "AI Chat": "/ai-chat",
      Reports: "/reports",
      Context: "/context-entries",
      Runbooks: "/case-runbooks",
      Admin: "/admin",
      Profile: "/profile",
      Logout: "/logout",
    };

    for (const [label, href] of Object.entries(destinations)) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }

    expect(screen.getByRole("button", { name: "Timezone (Local)" })).toBeInTheDocument();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows matching tooltip text on hover and keyboard focus", () => {
    renderDesktopSidebar();

    for (const label of [
      "Search",
      "Home",
      "Alerts",
      "Cases",
      "Tasks",
      "AI Chat",
      "Reports",
      "Context",
      "Runbooks",
      "Admin",
      "Timezone (Local)",
      "Profile",
      "Logout",
    ]) {
      const item = screen.getByLabelText(label, { exact: true });

      fireEvent.mouseEnter(item);
      expect(within(screen.getByRole("tooltip")).getByText(label)).toBeVisible();

      fireEvent.mouseLeave(item);
      expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

      fireEvent.focus(item);
      expect(within(screen.getByRole("tooltip")).getByText(label)).toBeVisible();
      fireEvent.blur(item);
    }
  });

  it("renders unassigned notification badges for work queue navigation items", () => {
    mockUseSidebarBadgeCounts.mockReturnValue({
      data: {
        alerts: { open: 7, unassigned: 2 },
        cases: { open: 3, unassigned: 1 },
        tasks: { open: 150, unassigned: 108 },
      },
    });

    renderDesktopSidebar();

    const alertsItem = screen.getByLabelText("Alerts");
    expect(within(alertsItem).getByText("2")).toBeVisible();

    const casesItem = screen.getByLabelText("Cases");
    expect(within(casesItem).getByText("1")).toBeVisible();

    const tasksItem = screen.getByLabelText("Tasks");
    expect(within(tasksItem).getByText("99+")).toBeVisible();

    expect(within(alertsItem).queryByText("O")).not.toBeInTheDocument();
    expect(within(alertsItem).queryByText("U")).not.toBeInTheDocument();
    expect(within(alertsItem).queryByText("7")).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("AI Chat")).queryByText("2")).not.toBeInTheDocument();
  });

  it("does not render notification badges when nothing is unassigned", () => {
    mockUseSidebarBadgeCounts.mockReturnValue({
      data: {
        alerts: { open: 2, unassigned: 0 },
        cases: { open: 1, unassigned: 0 },
        tasks: { open: 0, unassigned: 0 },
      },
    });

    renderDesktopSidebar();

    expect(within(screen.getByLabelText("Alerts")).queryByText("0")).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Alerts")).queryByText("2")).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Cases")).queryByText("1")).not.toBeInTheDocument();
  });
});
