import { expect, test, type Page, type Route } from "@playwright/test";

const now = "2026-01-01T00:00:00.000Z";

const adminUser = {
  id: "admin-user-id",
  username: "admin",
  email: "admin@example.com",
  full_name: "Admin User",
  role: "ADMIN",
  status: "ACTIVE",
  created_at: now,
  updated_at: now,
};

const emptyPage = {
  items: [],
  total: 0,
  page: 1,
  size: 50,
  pages: 0,
};

const sampleAlert = {
  id: 1,
  human_id: "ALT-0000001",
  title: "Production smoke alert",
  description: "Synthetic alert for production route smoke tests.",
  status: "NEW",
  priority: "LOW",
  source: "smoke",
  assignee: null,
  case_id: null,
  tags: [],
  timeline_items: {},
  created_at: now,
  updated_at: now,
};

const sampleCase = {
  id: 1,
  human_id: "CAS-0000001",
  title: "Production smoke case",
  description: "Synthetic case for production route smoke tests.",
  status: "NEW",
  priority: "LOW",
  assignee: null,
  tags: [],
  alerts: [],
  timeline_items: {},
  created_at: now,
  updated_at: now,
};

const sampleTask = {
  id: 1,
  human_id: "TSK-0000001",
  title: "Production smoke task",
  description: "Synthetic task for production route smoke tests.",
  status: "TODO",
  priority: "LOW",
  assignee: null,
  due_date: null,
  case_id: null,
  alert_id: null,
  tags: [],
  timeline_items: {},
  created_at: now,
  updated_at: now,
};

const routePaths = [
  "/",
  "/alerts",
  "/alerts/ALT-0000001",
  "/cases",
  "/cases/CAS-0000001",
  "/case-runbooks",
  "/tasks",
  "/tasks/TSK-0000001",
  "/reports",
  "/reports/ai-triage/details",
  "/search",
  "/admin",
  "/admin/users",
  "/admin/audit",
  "/admin/link-templates",
  "/admin/settings",
  "/admin/queue",
  "/ai-chat",
  "/profile",
  "/change-password",
] as const;

const fatalConsolePatterns = [
  /cannot access .* before initialization/i,
  /chunkloaderror/i,
  /failed to fetch dynamically imported module/i,
  /importing a module script failed/i,
  /does not provide an export/i,
  /minified react error/i,
  /unexpected token/i,
];

function jsonResponse(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

function metricsResponse() {
  return {
    summary: {},
    time_series: [],
    by_hour: [],
    by_source: [],
    by_priority: [],
    by_status: [],
    by_analyst: [],
    rejection_breakdown: [],
    confidence_distribution: [],
    weekly_trend: [],
    total: 0,
    items: [],
  };
}

function apiResponse(pathname: string): unknown {
  if (pathname === "/api/v1/auth/session") {
    return {
      user: adminUser,
      session: {
        id: "smoke-session",
        user_id: adminUser.id,
        created_at: now,
        expires_at: "2026-01-02T00:00:00.000Z",
      },
      mustChangePassword: false,
    };
  }

  if (pathname === "/api/v1/auth/oidc/config") {
    return { enabled: false, providerName: "SSO" };
  }

  if (pathname === "/api/v1/auth/passkeys") return [];
  if (pathname === "/api/v1/api-keys") return [];
  if (pathname === "/api/v1/features") return {};
  if (pathname === "/api/v1/settings/attachment-limits") {
    return {
      max_upload_size_mb: 50,
      max_image_preview_size_mb: 5,
      max_text_preview_size_mb: 1,
    };
  }

  if (pathname === "/api/v1/dashboard/stats") {
    return {
      unacknowledged_alerts: 0,
      open_cases: 0,
      open_tasks: 0,
    };
  }
  if (
    pathname === "/api/v1/dashboard/recent" ||
    pathname === "/api/v1/dashboard/priority-items"
  ) {
    return { items: [] };
  }

  if (pathname === "/api/v1/alerts") return emptyPage;
  if (/^\/api\/v1\/alerts\/\d+$/.test(pathname)) return sampleAlert;
  if (pathname === "/api/v1/cases") return emptyPage;
  if (/^\/api\/v1\/cases\/\d+$/.test(pathname)) return sampleCase;
  if (pathname === "/api/v1/case-runbooks") return emptyPage;
  if (pathname === "/api/v1/tasks") return emptyPage;
  if (/^\/api\/v1\/tasks\/\d+$/.test(pathname)) return sampleTask;

  if (pathname === "/api/v1/admin/auth/users/summary") return [adminUser];
  if (pathname === "/api/v1/admin/auth/users") return [adminUser];
  if (/^\/api\/v1\/admin\/auth\/users\/[^/]+\/passkeys$/.test(pathname)) {
    return [];
  }

  if (pathname === "/api/v1/admin/audit") return emptyPage;
  if (pathname === "/api/v1/admin/audit/event-types") return [];
  if (pathname === "/api/v1/admin/settings") return [];
  if (pathname === "/api/v1/admin/enrichments/maxmind/databases") return [];
  if (pathname === "/api/v1/admin/queue/jobs") return emptyPage;
  if (pathname === "/api/v1/admin/queue/stats") return [];
  if (pathname === "/api/v1/admin/queue/entrypoints") return [];

  if (pathname === "/api/v1/link-templates") return [];
  if (pathname === "/api/v1/search") {
    return { results: [], total: 0, limit: 25, offset: 0 };
  }

  if (pathname === "/api/v1/langflow/sessions") return [];
  if (pathname === "/api/v1/langflow/test-connection") {
    return { success: true, message: "Mocked by production smoke test", checks: [] };
  }

  if (pathname.startsWith("/api/v1/metrics")) return metricsResponse();

  return {};
}

async function installProductionApiMocks(page: Page) {
  await page.addInitScript(() => {
    class SmokeWebSocket {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;

      readonly CONNECTING = 0;
      readonly OPEN = 1;
      readonly CLOSING = 2;
      readonly CLOSED = 3;
      readonly readyState = SmokeWebSocket.CLOSED;

      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      addEventListener() {}
      removeEventListener() {}
      send() {}
      close() {}
    }

    window.WebSocket = SmokeWebSocket as unknown as typeof WebSocket;
  });

  await page.route("**/api/**", async (route: Route) => {
    const url = new URL(route.request().url());
    await route.fulfill(jsonResponse(apiResponse(url.pathname)));
  });
}

test("production bundle loads all major lazy routes", async ({ page }) => {
  const failures: string[] = [];

  await installProductionApiMocks(page);

  page.on("pageerror", (error) => {
    failures.push(`pageerror: ${error.stack || error.message}`);
  });

  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (fatalConsolePatterns.some((pattern) => pattern.test(text))) {
      failures.push(`console: ${text}`);
    }
  });

  page.on("response", (response) => {
    const url = response.url();
    const resourceType = response.request().resourceType();
    if (
      url.includes("/assets/") &&
      (resourceType === "script" || resourceType === "stylesheet") &&
      response.status() >= 400
    ) {
      failures.push(`asset ${response.status()}: ${url}`);
    }
  });

  page.on("requestfailed", (request) => {
    const url = request.url();
    const resourceType = request.resourceType();
    const errorText = request.failure()?.errorText || "";
    if (errorText.includes("ERR_ABORTED")) return;
    if (
      url.includes("/assets/") &&
      (resourceType === "script" || resourceType === "stylesheet")
    ) {
      failures.push(`asset request failed: ${url} ${errorText}`.trim());
    }
  });

  for (const routePath of routePaths) {
    await test.step(routePath, async () => {
      const response = await page.goto(routePath, { waitUntil: "domcontentloaded" });
      expect(response?.status(), `${routePath} document response`).toBeLessThan(400);

      await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => {});

      await expect
        .poll(
          async () => (await page.locator("#root").innerText()).trim(),
          {
            message: `${routePath} rendered non-empty root`,
            timeout: 10_000,
          }
        )
        .not.toBe("");

      const rootText = await page.locator("#root").innerText();
      expect(rootText, `${routePath} should not be stuck on auth loading`).not.toBe("Loading...");

      const routeFailures = failures.splice(0);
      expect(routeFailures, `${routePath} production runtime errors`).toEqual([]);
    });
  }
});
