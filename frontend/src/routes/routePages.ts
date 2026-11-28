import { lazy, type ComponentType } from "react";

function lazyPage(load: () => Promise<{ default: ComponentType }>) {
  // Navigation and speculative loads share the same in-flight import. A failed
  // speculative load must not leave a rejected promise for a later navigation.
  let pending: ReturnType<typeof load> | undefined;
  const loadOnce = () => pending ??= load().catch((error) => {
    pending = undefined;
    throw error;
  });

  return {
    Component: lazy(loadOnce),
    preload: () => loadOnce().then(() => undefined, () => undefined),
  };
}

const dashboardsPage = lazyPage(() => import("../pages/CustomDashboards"));
const alertsPage = lazyPage(() => import("../pages/Alerts"));

export const signedInPages = {
  "/": lazyPage(() => import("../pages/Home")),
  "/alerts": alertsPage,
  "/alerts/:humanId": alertsPage,
  "/cases": lazyPage(() => import("../pages/CaseList")),
  "/cases/:humanId": lazyPage(() => import("../pages/CaseDetail")),
  "/case-runbooks": lazyPage(() => import("../pages/CaseRunbooks")),
  "/tasks": lazyPage(() => import("../pages/TaskList")),
  "/tasks/:humanId": lazyPage(() => import("../pages/TaskDetail")),
  "/dashboards": dashboardsPage,
  "/dashboards/:dashboardId": dashboardsPage,
  "/reports": lazyPage(() => import("../pages/Reports")),
  "/search": lazyPage(() => import("../pages/SearchPage")),
  "/ai-chat": lazyPage(() => import("../pages/AIChat").then((module) => ({ default: module.AIChat }))),
  "/context-entries": lazyPage(() => import("../pages/ContextEntries")),
  "/profile": lazyPage(() => import("../pages/ProfileManagement")),
};

export const adminPages = {
  "/admin": lazyPage(() => import("../pages/Admin")),
  "/admin/audit": lazyPage(() => import("../pages/AdminAuditTrail")),
  "/admin/users": lazyPage(() => import("../pages/AdminUsers")),
  "/admin/link-templates": lazyPage(() => import("../pages/AdminLinkTemplates")),
  "/admin/settings": lazyPage(() => import("../pages/AdminSettings")),
  "/admin/queue": lazyPage(() => import("../pages/AdminQueueStatus")),
  "/reports/ai-triage/details": lazyPage(() => import("../pages/AITriageDetails")),
};

export const queuePreloadPaths = ["/alerts", "/cases", "/tasks"] as const;

const preloadPages = new Map(Object.entries({ ...signedInPages, ...adminPages }));

export function canSpeculativelyLoadRoutes() {
  const { connection } = navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
  };
  return !connection?.saveData && connection?.effectiveType !== "slow-2g" && connection?.effectiveType !== "2g";
}

export function preloadRoute(path: string) {
  if (canSpeculativelyLoadRoutes()) return preloadPages.get(path)?.preload();
}
