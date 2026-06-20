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

  const SidebarRailWithLabels = Object.assign(
    ({
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
    ),
    {
      NavItem: React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement> & {
          icon?: React.ReactNode;
          mobile?: boolean;
          selected?: boolean;
        }
      >(({ children, icon, mobile: _mobile, selected: _selected, ...props }, ref) => (
        <div ref={ref} data-testid="sidebar-nav-item" {...props}>
          {icon}
          <span>{children}</span>
        </div>
      )),
    },
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
    useViewTransitionNavigate: () => vi.fn(),
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

  it("does not render duplicate visible labels before a collapsed item is active", () => {
    renderDesktopSidebar();

    for (const label of [
      "Search",
      "Home",
      "Alerts",
      "Cases",
      "Tasks",
      "AI Chat",
      "Reports",
      "Admin",
      "Timezone (Local)",
      "Profile",
      "Logout",
    ]) {
      expect(screen.queryAllByText(label)).toHaveLength(1);
    }

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
      "Admin",
      "Timezone (Local)",
      "Profile",
      "Logout",
    ]) {
      const item = screen.getByLabelText(label);

      fireEvent.mouseEnter(item);
      expect(within(screen.getByRole("tooltip")).getByText(label)).toBeVisible();

      fireEvent.mouseLeave(item);
      expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

      fireEvent.focus(item);
      expect(within(screen.getByRole("tooltip")).getByText(label)).toBeVisible();
      fireEvent.blur(item);
    }
  });

  it("renders open and unassigned badges for work queue navigation items", () => {
    mockUseSidebarBadgeCounts.mockReturnValue({
      data: {
        alerts: { open: 7, unassigned: 2 },
        cases: { open: 3, unassigned: 1 },
        tasks: { open: 11, unassigned: 0 },
      },
    });

    renderDesktopSidebar();

    const alertsItem = screen.getByLabelText("Alerts");
    expect(within(alertsItem).getByText("O")).toBeVisible();
    expect(within(alertsItem).getByText("7")).toBeVisible();
    expect(within(alertsItem).getByText("U")).toBeVisible();
    expect(within(alertsItem).getByText("2")).toBeVisible();

    const casesItem = screen.getByLabelText("Cases");
    expect(within(casesItem).getByText("O")).toBeVisible();
    expect(within(casesItem).getByText("3")).toBeVisible();
    expect(within(casesItem).getByText("U")).toBeVisible();
    expect(within(casesItem).getByText("1")).toBeVisible();

    const tasksItem = screen.getByLabelText("Tasks");
    expect(within(tasksItem).getByText("O")).toBeVisible();
    expect(within(tasksItem).getByText("11")).toBeVisible();
    expect(within(tasksItem).queryByText("U")).not.toBeInTheDocument();

    expect(within(screen.getByLabelText("AI Chat")).queryByText("O")).not.toBeInTheDocument();
  });
});
