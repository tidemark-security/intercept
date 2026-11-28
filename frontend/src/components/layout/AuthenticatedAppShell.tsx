import { Suspense, useEffect } from "react";
import { Outlet } from "react-router-dom";
import { DefaultPageLayout, Loader } from "@tidemark-security/ux";

import { DesktopSidebar, MobileSidebar, SearchOverlay } from "./AppSidebar";
import { canSpeculativelyLoadRoutes, preloadRoute, queuePreloadPaths } from "@/routes/routePages";

function preloadWhenIdle(callback: () => void) {
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(callback);
    return () => window.cancelIdleCallback(id);
  }

  const id = window.setTimeout(callback, 1000);
  return () => window.clearTimeout(id);
}

function WarmQueueRoutes() {
  useEffect(() => {
    if (!canSpeculativelyLoadRoutes()) return;

    let stopped = false;
    let cancelIdle: (() => void) | undefined;
    const paths = queuePreloadPaths.values();

    function scheduleNext() {
      if (stopped || cancelIdle || document.hidden) return;
      const next = paths.next();
      if (next.done) return;
      cancelIdle = preloadWhenIdle(async () => {
        // Keep only one speculative queue import in flight.
        if (!document.hidden) await preloadRoute(next.value);
        cancelIdle = undefined;
        scheduleNext();
      });
    }

    document.addEventListener("visibilitychange", scheduleNext);
    scheduleNext();
    return () => {
      stopped = true;
      cancelIdle?.();
      document.removeEventListener("visibilitychange", scheduleNext);
    };
  }, []);

  return null;
}

export function AuthenticatedAppShell() {
  const fallback = (
    <div className="flex h-full w-full items-center justify-center bg-page-background">
      <Loader size="large" aria-label="Loading page" />
    </div>
  );

  return (
    <DefaultPageLayout
      desktopSidebar={<DesktopSidebar />}
      mobileSidebar={<MobileSidebar />}
      overlaySlot={<SearchOverlay />}
      contentClassName="overflow-hidden"
    >
      <Suspense fallback={fallback}>
        <Outlet />
        <WarmQueueRoutes />
      </Suspense>
    </DefaultPageLayout>
  );
}
