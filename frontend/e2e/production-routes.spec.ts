import { expect, test, type BrowserContext, type Locator, type Page, type Route } from "@playwright/test";
import type { RecommendationStatus } from "../src/types/generated/models/RecommendationStatus";

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

const secondAlert = { ...sampleAlert, id: 2, human_id: "ALT-0000002", title: "Second smoke alert" };

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

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
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

  if (pathname === "/api/v1/alerts") return { ...emptyPage, items: [sampleAlert, secondAlert], total: 2, pages: 1 };
  if (pathname === "/api/v1/alerts/1") return sampleAlert;
  if (pathname === "/api/v1/alerts/2") return secondAlert;
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
  if (pathname === "/api/v1/admin/enrichments/providers") {
    return [
      {
        provider_id: "entra_id",
        display_name: "Microsoft Entra ID",
        settings_prefix: "enrichment.entra_id",
        enabled: false,
        supports_bulk_sync: true,
        item_types: ["internal_actor"],
        cache_entry_count: 0,
        alias_count: 0,
        last_activity_at: null,
      },
      {
        provider_id: "google_workspace",
        display_name: "Google Workspace",
        settings_prefix: "enrichment.google_workspace",
        enabled: false,
        supports_bulk_sync: true,
        item_types: ["internal_actor"],
        cache_entry_count: 0,
        alias_count: 0,
        last_activity_at: null,
      },
      {
        provider_id: "ldap",
        display_name: "LDAP",
        settings_prefix: "enrichment.ldap",
        enabled: false,
        supports_bulk_sync: true,
        item_types: ["internal_actor"],
        cache_entry_count: 0,
        alias_count: 0,
        last_activity_at: null,
      },
    ];
  }
  if (pathname === "/api/v1/admin/queue/jobs") return emptyPage;
  if (pathname === "/api/v1/admin/queue/stats") return [];
  if (pathname === "/api/v1/admin/queue/entrypoints") return [];

  if (pathname === "/api/v1/link-templates") return [];
  if (pathname === "/api/v1/personal-link-templates") return [];
  if (pathname === "/api/v1/link-templates/resolve") return [];
  if (pathname === "/api/v1/search") {
    return { results: [], total: 0, limit: 25, offset: 0 };
  }

  if (pathname === "/api/v1/langflow/sessions") return [];
  if (pathname === "/api/v1/langflow/test-connection") {
    return { success: true, message: "Mocked by production smoke test", checks: [] };
  }

  if (pathname === "/api/v1/mcp/oauth/clients") return [];

  if (pathname.startsWith("/api/v1/metrics")) return metricsResponse();

  return {};
}

async function installProductionApiMocks(target: Page | BrowserContext) {
  await target.addInitScript(() => {
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

  await target.route("**/api/**", async (route: Route) => {
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

      const loadFailures = failures.splice(0);
      expect(loadFailures, `${routePath} production runtime errors`).toEqual([]);

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
      expect(rootText, `${routePath} should not be stuck on auth loading`).not.toBe("Checking your session…");

      const routeFailures = failures.splice(0);
      expect(routeFailures, `${routePath} production runtime errors`).toEqual([]);
    });
  }
});

test("sidebar links support new tabs and normal navigation", async ({ page, context }) => {
  await installProductionApiMocks(context);
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto("/alerts");

  const logo = page.getByRole("link", { name: "Tidemark home" });
  const home = page.getByRole("link", { name: "Home", exact: true });
  const search = page.getByRole("link", { name: "Search", exact: true });
  await expect(home).toHaveAttribute("href", "/");
  await expect(logo).toHaveAttribute("href", "/");
  await expect(search).toHaveAttribute("href", "/search");

  const [homeTab] = await Promise.all([
    context.waitForEvent("page"),
    logo.click({ button: "middle" }),
  ]);
  await expect(homeTab).toHaveURL(/\/$/);
  await homeTab.close();
  const [searchTab] = await Promise.all([
    context.waitForEvent("page"),
    search.click({ modifiers: ["ControlOrMeta"] }),
  ]);
  await expect(searchTab).toHaveURL((url) => url.pathname === "/search");
  await searchTab.close();
  await expect(page).toHaveURL(/\/alerts$/);

  await search.press("Enter");
  await expect(page).toHaveURL((url) => url.pathname === "/search");
  await expect(search).toHaveAttribute("aria-current", "page");
  await logo.click();
  await expect(page).toHaveURL(/\/$/);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("link", { name: "Alerts", exact: true })).toHaveAttribute("href", "/alerts");
  await page.getByRole("button", { name: "More navigation" }).click();
  for (const [label, href] of [["Search", "/search"], ["Admin", "/admin"], ["Profile", "/profile"], ["Logout", "/logout"]]) {
    const item = page.getByRole("menuitem", { name: label, exact: true });
    await expect(item).toHaveJSProperty("tagName", "A");
    await expect(item).toHaveAttribute("href", href);
  }
});

function pageModuleRequest(name: string) {
  // These smoke tests also run against the local Vite development server.
  return new RegExp(`/((src/pages/${name}\\.tsx)|(assets/${name}-[\\w-]+\\.js))(?:\\?.*)?$`);
}

for (const width of [1440, 390]) {
  test(`navigation stays mounted during a cold route load at ${width}px`, async ({ page }) => {
    await installProductionApiMocks(page);
    await page.setViewportSize({ width, height: 900 });

    let releaseReports!: () => void;
    const reportsGate = new Promise<void>((resolve) => { releaseReports = resolve; });
    let reportsRequested = false;
    const reportsModule = pageModuleRequest("Reports");
    await page.route(reportsModule, async (route) => {
      reportsRequested = true;
      await reportsGate;
      await route.continue();
    });

    try {
      await page.goto("/alerts");
      const reports = page.getByRole("link", { name: "Reports", exact: true });
      const home = page.getByRole("link", { name: "Home", exact: true });
      const originalHome = await home.elementHandle();
      expect(reportsRequested).toBe(false);

      await reports.focus();
      await expect.poll(() => reportsRequested, { message: "Focus should preload Reports before navigating" }).toBe(true);
      await expect(page).toHaveURL(/\/alerts$/);

      await reports.press("Enter");
      await expect(page).toHaveURL(/\/reports$/);
      await expect(page.getByRole("status", { name: "Loading page" })).toBeVisible();
      await expect(home).toBeVisible();
      await expect(reports).toBeFocused();
      await expect(reports).toHaveAttribute("aria-current", "page");

      releaseReports();
      await expect(page.getByText("SOC operational metrics and performance analysis")).toBeVisible();
      await expect(page.getByRole("status", { name: "Loading page" })).toHaveCount(0);
      expect(await home.evaluate((node, original) => node === original, originalHome)).toBe(true);
      await originalHome.dispose();
    } finally {
      releaseReports();
    }
  });
}

test("idle preloading warms queue code without making queue API requests", async ({ page }) => {
  await installProductionApiMocks(page);
  const listCode = ["Alerts", "CaseList", "TaskList"].map(pageModuleRequest);
  const preloaded = new Set<RegExp>();
  const queueCalls: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (/^\/api\/v1\/(alerts|cases|tasks)$/.test(path)) queueCalls.push(path);
  });
  page.on("response", (response) => {
    if (!response.ok()) return;
    for (const match of listCode) {
      if (match.test(response.url())) preloaded.add(match);
    }
  });

  await page.goto("/reports");
  await expect.poll(() => preloaded.size).toBe(listCode.length);
  await expect(page).toHaveURL((url) => url.pathname === "/reports");
  expect(queueCalls).toEqual([]);
});

test("admin route access stays gated inside the signed-in shell", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.route("**/api/v1/auth/session", (route) => route.fulfill(jsonResponse({
    ...apiResponse("/api/v1/auth/session") as Record<string, unknown>,
    user: { ...adminUser, role: "ANALYST" },
  })));
  const adminModule = pageModuleRequest("AdminUsers");
  const requestedAdminModules: string[] = [];
  page.on("request", (request) => {
    if (adminModule.test(request.url())) requestedAdminModules.push(request.url());
  });

  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "Access Denied" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Home", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Admin", exact: true })).toHaveCount(0);
  expect(requestedAdminModules).toEqual([]);
});

for (const width of [1920, 1024, 390]) {
  test(`AI triage state changes preserve alert layout at ${width}px`, async ({ page }) => {
    await installProductionApiMocks(page);
    await page.route("**/api/v1/features", (route) => route.fulfill(jsonResponse({ ai_triage_enabled: true })));

    let status: RecommendationStatus | null = null;
    const failure = width === 390
      ? "Retries exhausted: All connection attempts failed. ".repeat(18).trim()
      : "Retries exhausted";
    const contextEntry = { id: 17, body: "Previously supplied context", author: "admin", criteria: [] };
    const recommendation = {
      id: 1,
      alert_id: 1,
      created_at: now,
      created_by: "tidemark_ai",
      disposition: "NEEDS_INVESTIGATION",
      confidence: 0.8,
      request_escalate_to_case: true,
      suggested_status: "ESCALATED",
      suggested_priority: "MEDIUM",
      suggested_assignee: "analyst",
      suggested_tags_add: ["network", "endpoint"],
      suggested_tags_remove: ["unverified"],
      reasoning_bullets: [
        "The evidence is incomplete.",
        ...Array.from({ length: 14 }, (_, index) => `Evidence detail ${index + 1}`),
      ],
      recommended_actions: [{ title: "Pull DNS telemetry" }],
      applied_context_entries: [contextEntry],
      context_snapshot_verified: true,
      error_message: failure,
      rejection_reason: "The alert needs a different disposition.",
    };
    await page.route(/\/api\/v1\/alerts\/1(?:\?|$)/, (route) => route.fulfill(jsonResponse({
      ...sampleAlert,
      triage_context_changed: true,
      triage_recommendation: status ? { ...recommendation, status } : null,
    })));
    await page.route("**/api/v1/alerts/1/triage-recommendation/enqueue", (route) => {
      status = "QUEUED";
      return route.fulfill(jsonResponse({ ...recommendation, status }));
    });
    await page.route("**/api/v1/alerts/1/triage-recommendation/accept", (route) => {
      status = "ACCEPTED";
      return route.fulfill(jsonResponse({ recommendation: { ...recommendation, status } }));
    });

    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/alerts/${sampleAlert.human_id}`);
    const timeline = page.getByLabel("alert timeline content");
    const card = timeline.locator("section[data-layout]");
    const metadata = timeline.getByText("Source", { exact: true });
    const request = card.getByRole("button", { name: "Request AI Triage" });
    const retry = card.getByRole("button", { name: "Retry AI Triage" });
    const measurements = new Map<string, { height: number; metadataOffset: number }>();
    const preferredLayout = width === 1920 ? "compact" : "expanded";

    const setLayout = async (layout: "compact" | "expanded") => {
      if (await card.getAttribute("data-layout") !== layout) {
        await card.getByRole("button", { name: layout === "compact"
          ? "Collapse triage recommendation" : "Expand triage recommendation" }).click();
      }
      await expect(card).toHaveAttribute("data-layout", layout);
    };
    const verifyRobotMotion = async (state: "available" | "in-progress" | "failed") => {
      const illustration = card.locator(`[data-robot-state="${state}"]`);
      await expect(illustration.locator("svg.lucide-bot")).toBeInViewport({ ratio: 1 });
      await expect(illustration.locator("svg:not(.lucide-bot)")).toHaveCount(state === "in-progress" ? 6 : 0);
      const hasRunningAnimation = () => illustration.evaluate((element) =>
        element.getAnimations({ subtree: true }).some((animation) => animation.playState === "running"));
      await page.emulateMedia({ reducedMotion: "reduce" });
      await expect.poll(hasRunningAnimation).toBe(false);
      await page.emulateMedia({ reducedMotion: "no-preference" });
      await expect.poll(() => illustration.evaluate((element) =>
        element.getAnimations({ subtree: true }).some((animation) =>
          animation.playState === "running" && animation.effect?.getTiming().iterations === Infinity))).toBe(true);
    };
    const verifySize = async (title: string, borderStyle = "solid", mayGrow = false) => {
      await expect(card.getByRole("heading", { name: title, exact: true })).toBeVisible();
      await expect(card).toHaveAttribute("data-layout", preferredLayout);
      await expect(card).toHaveCSS("border-top-style", borderStyle);
      for (const layout of ["compact", "expanded"] as const) {
        await setLayout(layout);
        const bounds = (await card.boundingBox())!;
        const metadataBounds = (await metadata.boundingBox())!;
        const measurement = { height: bounds.height, metadataOffset: metadataBounds.y - bounds.y };
        const initial = measurements.get(layout);
        if (initial) {
          const growth = measurement.height - initial.height;
          if (mayGrow) expect(growth).toBeGreaterThanOrEqual(0);
          else expect(growth, `${title} (${layout}) should fit the shared minimum height`).toBeCloseTo(0, 0);
          expect(measurement.metadataOffset - initial.metadataOffset).toBeCloseTo(growth, 0);
        } else {
          measurements.set(layout, measurement);
        }
        expect(await card.evaluate((element) => element.scrollWidth - element.clientWidth)).toBe(0);
        const body = card.getByRole("group", { name: layout === "expanded" ? "Triage details" : "Triage summary", exact: true });
        await expect(body).toHaveCSS("overflow-y", "visible");
        if (title === "AI Triage Available") {
          const headerBounds = (await card.locator("header").boundingBox())!;
          const bodyBounds = (await body.boundingBox())!;
          const requestBounds = (await request.boundingBox())!;
          const gapAboveBody = bodyBounds.y - (headerBounds.y + headerBounds.height);
          const gapBelowBody = requestBounds.y - (bodyBounds.y + bodyBounds.height);
          expect(gapBelowBody).toBeCloseTo(gapAboveBody, 0);
          expect(bounds.y + bounds.height - (requestBounds.y + requestBounds.height))
            .toBeCloseTo(headerBounds.y - bounds.y, 0);
        }
      }
      await setLayout(preferredLayout);
    };

    await expect(request).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(card).toHaveAttribute("data-layout", "compact");
    await setLayout(preferredLayout);
    await verifySize("AI Triage Available", "dashed");
    await verifyRobotMotion("available");
    await expect(request.locator("svg.lucide-sparkles")).toBeVisible();
    await request.click();
    await verifySize("AI Triage In Progress");
    const progress = card.getByRole("status");
    await expect(progress).toHaveText("The recommendation will appear automatically when ready.");
    await verifyRobotMotion("in-progress");
    status = "FAILED";
    await verifySize("AI Triage Failed", "solid", width === 390);
    await verifyRobotMotion("failed");
    const diagnosticHint = card.getByText(/look up the alert ID in the triage worker logs/);
    const failureMessage = card.getByText(failure, { exact: true });
    for (const layout of ["compact", "expanded"] as const) {
      await setLayout(layout);
      await expect(failureMessage).toBeInViewport();
      if (layout === "expanded" && width === 390) {
        expect((await card.boundingBox())!.height).toBeGreaterThan(measurements.get(layout)!.height);
        await diagnosticHint.scrollIntoViewIfNeeded();
      }
      await expect(diagnosticHint).toBeInViewport({ ratio: 1 });
      const header = (await card.locator("header").boundingBox())!;
      const cardBounds = (await card.boundingBox())!;
      const retryBounds = (await retry.boundingBox())!;
      const topInset = header.y - cardBounds.y;
      const bottomInset = cardBounds.y + cardBounds.height - (retryBounds.y + retryBounds.height);
      expect(retryBounds.x).toBeCloseTo(header.x, 0);
      expect(bottomInset).toBeCloseTo(topInset, 0);
    }
    await setLayout(preferredLayout);
    await expect(retry).toBeEnabled();
    await retry.click();
    await expect(card.getByRole("heading", { name: "AI Triage In Progress" })).toBeVisible();
    status = "PENDING";
    await verifySize("AI Triage Recommendation", "solid", true);
    await setLayout("expanded");
    const action = card.getByText("Escalate to case and investigate", { exact: true });
    await expect(action).toBeInViewport({ ratio: 1 });
    await expect(action.locator("..").locator("..")).toHaveCSS("padding-bottom", "2px");
    for (const title of ["Context at Triage", "Reasoning", "Recommended Changes", "Recommended Tasks"]) {
      const accordion = card.getByRole("button", { name: new RegExp(`^${title}`) });
      const label = accordion.getByText(title, { exact: true });
      const titlePosition = async () => {
        const cardBounds = (await card.boundingBox())!;
        const labelBounds = (await label.boundingBox())!;
        return { x: labelBounds.x - cardBounds.x, y: labelBounds.y - cardBounds.y };
      };
      await expect(accordion).toHaveAttribute("aria-expanded", "false");
      await expect(accordion).toBeInViewport({ ratio: 1 });
      const closedPosition = await titlePosition();
      await accordion.click();
      await expect(accordion).toHaveAttribute("aria-expanded", "true");
      const openPosition = await titlePosition();
      expect(openPosition.x).toBeCloseTo(closedPosition.x, 0);
      expect(openPosition.y).toBeCloseTo(closedPosition.y, 0);
      await accordion.click();
    }
    await setLayout(preferredLayout);
    await card.getByRole("button", { name: "Accept Recommendation" }).click();
    await expect(card.getByText("Accepted", { exact: true })).toBeVisible();
    await verifySize("AI Triage Recommendation");

    await setLayout("expanded");
    await card.getByRole("button", { name: /^Reasoning/ }).click();
    await expect(card.getByText("Evidence detail 14", { exact: true })).toBeVisible();
    expect((await card.boundingBox())!.height).toBeGreaterThan(measurements.get("expanded")!.height);
    await expect(card.getByRole("group", { name: "Triage details", exact: true })).toHaveCSS("overflow-y", "visible");

    await setLayout(preferredLayout);
    for (const [reviewedStatus, label] of [["REJECTED", "Rejected"], ["SUPERSEDED", "Superseded"]] as const) {
      status = reviewedStatus;
      await page.reload();
      await expect(card.getByText(label, { exact: true })).toBeVisible();
      await verifySize("AI Triage Recommendation", "solid", true);
    }
  });
}

const assigneeFilterRoutes = [
  { resource: "alerts", sample: sampleAlert, prefix: "ALT" },
  { resource: "cases", sample: sampleCase, prefix: "CAS" },
  { resource: "tasks", sample: sampleTask, prefix: "TSK" },
] as const;

for (const { resource, sample, prefix } of assigneeFilterRoutes) {
  test(`${resource} returns the selected assignees in either order and updates when they are removed`, async ({ page }) => {
    await installProductionApiMocks(page);
    const analystA = { userId: "analyst-a-id", username: "analyst-a" };
    const analystB = { userId: "analyst-b-id", username: "analyst-b" };
    const rows = [
      { ...sample, title: "Unassigned item", assignee: null },
      { ...sample, title: "Analyst A item", assignee: analystA.username, id: 2, human_id: `${prefix}-0000002` },
      { ...sample, title: "Analyst B item", assignee: analystB.username, id: 3, human_id: `${prefix}-0000003` },
    ];
    await page.route("**/api/v1/admin/auth/users/summary**", (route) => route.fulfill(jsonResponse([analystA, analystB])));
    await page.route(new RegExp(`/api/v1/${resource}(?:\\?|$)`), (route) => {
      const assignees = new URL(route.request().url()).searchParams.getAll("assignee");
      const items = assignees.length === 0 ? rows : rows.filter(({ assignee }) => assignees.includes(assignee ?? "__unassigned__"));
      return route.fulfill(jsonResponse({ ...emptyPage, items, total: items.length, pages: 1 }));
    });

    await page.setViewportSize({ width: 1640, height: 900 });
    await page.goto(`/${resource}`);
    const filtersButton = page.getByRole("button", { name: /^Filters/ });
    const filterPanel = page.getByRole("dialog", { name: "Queue filters" });
    const trigger = page.getByRole("button", { name: /^Assignee/ });
    const entityLinks = page.locator(`a[href^="/${resource}/${prefix}-"]`);
    const choose = async (name: string) => {
      const option = page.getByRole("menuitem", { name, exact: true });
      if (!await option.isVisible()) {
        if (!await filterPanel.isVisible()) await filtersButton.click();
        await trigger.click();
      }
      await option.click();
    };
    const expectItems = async (...titles: string[]) => {
      await expect(entityLinks).toHaveCount(titles.length);
      for (const title of titles) await expect(entityLinks.filter({ hasText: title })).toBeVisible();
    };
    await expectItems("Unassigned item", "Analyst A item", "Analyst B item");
    await choose("Unassigned");
    await choose("analyst-a");
    await expect(trigger).toContainText("2 assignees");
    await expectItems("Unassigned item", "Analyst A item");

    await choose("analyst-a");
    await expectItems("Unassigned item");
    await choose("Clear selection");
    await choose("analyst-a");
    await choose("Unassigned");
    await expectItems("Unassigned item", "Analyst A item");

    await choose("analyst-a");
    await expectItems("Unassigned item");
    await choose("Clear selection");
    await choose("analyst-b");
    await choose("analyst-a");
    await expectItems("Analyst A item", "Analyst B item");
    await choose("analyst-b");
    await expectItems("Analyst A item");

    const filters = new URLSearchParams({
      status: sample.status,
      start_date: "2026-01-01T00:00:00Z",
      end_date: "2026-01-02T00:00:00Z",
      include_tags: "incident",
      exclude_tags: "internal",
    });
    const request = page.waitForRequest((req) => {
      const url = new URL(req.url());
      return url.pathname === `/api/v1/${resource}` && url.searchParams.has("start_date");
    });
    await page.goto(`/${resource}?${filters}&assignee=__unassigned__,${analystA.username}`);
    const actual = new URL((await request).url()).searchParams;
    expect(actual.getAll("assignee").sort()).toEqual(["__unassigned__", analystA.username].sort());
    for (const [key, value] of filters) expect(actual.get(key)).toBe(value);

    await expect(filtersButton).toHaveAccessibleName("Filters, 6 active");
    await page.getByRole("button", { name: "Remove assignee Unassigned", exact: true }).click();
    await expect(filtersButton).toHaveAccessibleName("Filters, 5 active");
    await expect(page).toHaveURL((url) => url.searchParams.get("assignee") === analystA.username);
    await expect(page).toHaveURL((url) => url.searchParams.get("include_tags") === "incident");
  });
}

test("queue filters float over the compact list with independent sorting and clear controls", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.route(/\/api\/v1\/tasks(?:\?|$)/, (route) =>
    route.fulfill(jsonResponse({ ...emptyPage, items: [sampleTask], total: 1, pages: 1 })),
  );
  await page.addInitScript(() => localStorage.setItem("intercept-ai-pane-width", "320"));
  await page.setViewportSize({ width: 1372, height: 900 });
  await page.goto("/tasks");

  const filters = page.getByRole("button", { name: /^Filters/ });
  const panel = page.getByRole("dialog", { name: "Queue filters" });
  const sort = page.getByRole("button", { name: /^Sort/ });
  const card = page.getByRole("link", { name: /Production smoke task/ });
  await expect(card).toBeVisible();
  await expect(filters).toHaveAccessibleName("Filters");
  const originalY = (await card.boundingBox())!.y;

  await sort.click();
  await page.getByRole("menuitem", { name: "Oldest first", exact: true }).click();
  await expect(sort).toHaveAccessibleName("Sort Oldest first");
  await filters.press("Enter");
  await expect(panel).toBeVisible();
  expect((await panel.boundingBox())!.width).toBeLessThanOrEqual(320);
  expect((await card.boundingBox())!.y).toBeCloseTo(originalY, 0);

  await panel.getByRole("button", { name: "Time All time" }).click();
  await page.getByText("Last 7 days", { exact: true }).click();
  await expect(panel.getByRole("button", { name: "Time Last 7 days" })).toBeVisible();

  await panel.getByRole("button", { name: "Tags No tags" }).click();
  const tagInput = page.getByPlaceholder("Add include tag");
  await tagInput.fill("incident");
  await tagInput.press("Enter");
  await expect(page).toHaveURL((url) => url.searchParams.get("include_tags") === "incident");
  await tagInput.press("Escape");
  await expect(panel).toBeVisible();

  await panel.getByRole("button", { name: "Done", exact: true }).click();
  await expect(filters).toBeFocused();
  await expect(filters).toHaveAccessibleName("Filters, 2 active");
  await page.getByRole("button", { name: "Remove include tag incident", exact: true }).click();
  await expect(filters).toHaveAccessibleName("Filters, 1 active");
  await filters.click();
  await panel.getByRole("button", { name: "Clear all", exact: true }).click();
  await expect(filters).toHaveAccessibleName("Filters");
  await expect(sort).toHaveAccessibleName("Sort Oldest first");
  await expect(page).toHaveURL((url) => url.searchParams.get("sort_order") === "asc" && !url.searchParams.has("timeframe"));
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(filters).toBeFocused();

  for (const width of [360, 800, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await filters.click();
    await expect(panel).toBeVisible();
    const bounds = (await panel.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await panel.getByRole("button", { name: "Done", exact: true }).click();
  }
});

const wideSplitRoutes = [
  { name: "Alerts", path: "/alerts/ALT-0000001", entity: "alert", railLabel: "Resize alert list", list: "alerts", item: sampleAlert },
  { name: "Cases list", path: "/cases", entity: "case", railLabel: "Resize case list", list: "cases", item: sampleCase },
  { name: "Tasks list", path: "/tasks", entity: "task", railLabel: "Resize task list", list: "tasks", item: sampleTask },
  { name: "Case detail", path: "/cases/CAS-0000001", entity: "case", railLabel: "Resize assistant pane" },
  { name: "Task detail", path: "/tasks/TSK-0000001", entity: "task", railLabel: "Resize assistant pane" },
] as const;

for (const split of wideSplitRoutes) {
  test(`wide ${split.name} divider tracks the pointer and saves the clamped width on release`, async ({ page }) => {
    const widthKey = "intercept-ai-pane-width";
    await installProductionApiMocks(page);
    if ("list" in split) {
      const prefix = split.item.human_id.split("-")[0];
      const items = Array.from({ length: 50 }, (_, index) => ({
        ...split.item,
        id: index + 1,
        human_id: `${prefix}-${String(index + 1).padStart(7, "0")}`,
        tags: ["smoke", "triage", "resize"],
      }));
      await page.route(new RegExp(`/api/v1/${split.list}(?:\\?|$)`), (route) =>
        route.fulfill(jsonResponse({ ...emptyPage, items, total: items.length, pages: 1 })),
      );
    }
    await page.addInitScript(({ key }) => {
      if (localStorage.getItem(key) === null) localStorage.setItem(key, "640");
    }, { key: widthKey });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(split.path);
    if ("list" in split) {
      const links = page.locator(`a[href^="/${split.list}/"]`);
      await expect(links).toHaveCount(50);
      if (split.path === `/${split.list}`) await links.first().click();
    }
    const timeline = page.getByLabel(`${split.entity} timeline content`);
    await expect(timeline).toBeVisible();
    await expect(page.locator('[class~="bg-p4/60"]').locator('..')).toHaveCSS("opacity", "0.45");

    const rail = page.getByRole("separator", { name: split.railLabel });
    const start = await rail.boundingBox();
    if (!start) throw new Error("Expected the wide split divider");

    const x = start.x + start.width / 2;
    const y = start.y + start.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x - 80, y);
    await page.evaluate(() => new Promise(requestAnimationFrame));
    const tracking = await rail.boundingBox();
    expect(tracking?.x).toBeCloseTo(start.x - 80, 0);
    expect(await page.evaluate((key) => localStorage.getItem(key), widthKey)).toBe("640");

    await page.mouse.move(x + 140, y, { steps: 4 });
    await expect(rail).toBeVisible();
    expect(await page.evaluate((key) => localStorage.getItem(key), widthKey)).toBe("640");
    await page.mouse.up();
    expect(await page.evaluate((key) => localStorage.getItem(key), widthKey)).toBe("706");
    const detail = await timeline.boundingBox();
    expect(detail?.width).toBeGreaterThanOrEqual(600);

    await page.reload();
    await expect(rail).toHaveAttribute("aria-valuenow", "706");
    await rail.press("ArrowLeft");
    await expect(rail).toHaveAttribute("aria-valuenow", "690");
    expect(await page.evaluate((key) => localStorage.getItem(key), widthKey)).toBe("690");

    const beforeCancel = await rail.boundingBox();
    if (!beforeCancel) throw new Error("Expected the divider to remain visible after reload");
    const cancelX = beforeCancel.x + beforeCancel.width / 2;
    await page.mouse.move(cancelX, y);
    await page.mouse.down();
    await page.mouse.move(cancelX - 120, y);
    await page.keyboard.press("Escape");
    await page.mouse.up();
    expect((await rail.boundingBox())?.x).toBe(beforeCancel.x);
    expect(await page.evaluate((key) => localStorage.getItem(key), widthKey)).toBe("690");

    if (!("list" in split)) {
      await rail.click();
      await expect(rail).toHaveCount(0);
      await expect(timeline).toBeVisible();
    }
  });
}

async function measureHeaderCollapse(page: Page, humanId: string, collapseTargets: Locator[]) {
  const entityId = page.getByRole("heading", { level: 1, name: humanId });
  const lastAction = collapseTargets.at(-1)!;
  const titleRow = page.locator("div.min-h-9").filter({ has: lastAction }).locator("..");
  const labelWidth = (button: Locator) => button.locator(":scope > span:not(:has(svg))").evaluate((label) => label.getBoundingClientRect().width);
  await expect(lastAction).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const { titleReserve, actionsWidth } = await lastAction.evaluate((button) => {
    const actions = button.closest("div.min-h-9")!;
    const row = actions.parentElement!;
    const rowStyle = getComputedStyle(row);
    return {
      titleReserve: Number.parseFloat(getComputedStyle(row.firstElementChild!).minWidth) + Number.parseFloat(rowStyle.columnGap),
      actionsWidth: Number.parseFloat(getComputedStyle(actions).width),
    };
  });
  const actionsBesideTitle = async () => {
    const id = (await entityId.boundingBox())!;
    const action = (await lastAction.boundingBox())!;
    return action.y < id.y + id.height && action.y + action.height > id.y;
  };

  for (const button of collapseTargets) await expect(button).toHaveCSS("height", "36px");
  for (const button of collapseTargets) expect(await labelWidth(button)).toBeGreaterThan(1);
  expect(await actionsBesideTitle()).toBe(true);

  const requiredWidths = [actionsWidth];
  for (const button of collapseTargets) {
    const fullWidth = await button.evaluate((element) => element.getBoundingClientRect().width);
    requiredWidths.push(requiredWidths.at(-1)! - (fullWidth - 36));
  }
  const setTitleRowWidth = (width?: number) => titleRow.evaluate((row, pixels) => {
    row.style.width = pixels === undefined ? "" : `${pixels}px`;
  }, width);
  const resizeToIcons = async (count: number) => {
    // Aim between adjacent layouts' minimum widths, so exactly count icons fit.
    const available = count === 0 ? requiredWidths[0] + 12 : (requiredWidths[count - 1] + requiredWidths[count]) / 2;
    await setTitleRowWidth(titleReserve + available);
    await expect.poll(async () => Promise.all(collapseTargets.map(async (button) => (await labelWidth(button)) <= 1)))
      .toEqual(collapseTargets.map((_, index) => index < count));
    for (const button of collapseTargets) await expect(button).toHaveCSS("height", "36px");
    expect(await actionsBesideTitle()).toBe(true);
  };

  return {
    resizeToIcons,
    reset: () => setTitleRowWidth(),
    shrinkPastInline: async () => {
      await setTitleRowWidth(titleReserve + requiredWidths.at(-1)! - 12);
      await expect.poll(actionsBesideTitle).toBe(false);
    },
  };
}

test("alert header collapses Link, Close, Assignee, and Escalate in that order", async ({ page }) => {
  await installProductionApiMocks(page);
  const assignee = "lead-investigator";
  await page.route(/\/api\/v1\/alerts\/1(?:\?|$)/, (route) => route.fulfill(jsonResponse({
    ...sampleAlert,
    assignee,
    triage_recommendation: {
      id: 1,
      alert_id: 1,
      created_at: now,
      created_by: "tidemark_ai",
      status: "PENDING",
      disposition: "NEEDS_INVESTIGATION",
      confidence: 0.8,
      request_escalate_to_case: true,
      suggested_status: "ESCALATED",
    },
  })));
  await page.addInitScript(() => localStorage.setItem("intercept-ai-pane-width", "400"));
  await page.setViewportSize({ width: 1540, height: 1000 });
  await page.goto("/alerts/ALT-0000001");

  const assign = page.getByRole("button", { name: assignee, exact: true });
  const close = page.getByRole("button", { name: /^Close Alert/ });
  const link = page.getByRole("button", { name: "Link to Case", exact: true });
  const escalate = page.getByRole("button", { name: "Escalate to case", exact: true });
  const collapseTargets = [link, close, assign, escalate];
  const { resizeToIcons, shrinkPastInline } = await measureHeaderCollapse(page, sampleAlert.human_id, collapseTargets);
  for (const count of [1, 2, 3, 4]) await resizeToIcons(count);
  for (const button of collapseTargets) await expect(button).toHaveCSS("width", "36px");
  await expect(escalate.locator("svg.lucide-arrow-right")).toBeVisible();
  await shrinkPastInline();
  await resizeToIcons(4);

  await assign.press("Enter");
  await expect(page.getByRole("menuitem", { name: /Assign to me/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(assign).toBeFocused();
  await close.click();
  await expect(close).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("menuitem", { name: /Closed \(False Positive\)/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(close).toBeFocused();
  await link.click();
  await expect(page.getByRole("dialog").getByText("Link to Case", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await escalate.click();
  await expect(page.getByRole("menuitem", { name: /Use AI recommendation/ })).toBeVisible();
  await page.keyboard.press("Escape");
  for (const count of [3, 2, 1, 0]) await resizeToIcons(count);
});

for (const { entity, resource, sample, closedStatus } of [
  { entity: "Case", resource: "cases", sample: sampleCase, closedStatus: "CLOSED" },
  { entity: "Task", resource: "tasks", sample: sampleTask, closedStatus: "DONE" },
]) {
  test(`${entity} header shares compact inline actions and filter overflow`, async ({ page }) => {
    await installProductionApiMocks(page);
    const assignee = "lead-investigator-with-a-long-username@example.test";
    let status = sample.status;
    await page.route(new RegExp(`/api/v1/${resource}/1(?:\\?|$)`), (route) =>
      route.fulfill(jsonResponse({ ...sample, status, assignee })),
    );
    await page.setViewportSize({ width: 1650, height: 900 });
    await page.goto(`/${resource}/${sample.human_id}`);

    const assign = page.getByRole("button", { name: assignee, exact: true });
    const edit = page.getByRole("button", { name: "Edit", exact: true });
    const close = page.getByRole("button", { name: new RegExp(`^Close ${entity}`) });
    const controls = page.getByRole("button", { name: "Timeline controls" });
    const filters = page.getByRole("radio", { name: "All Items", exact: true });
    const detailHeader = await measureHeaderCollapse(page, sample.human_id, [edit, close, assign]);
    for (const count of [1, 2, 3]) await detailHeader.resizeToIcons(count);
    await detailHeader.reset();
    await page.setViewportSize({ width: 800, height: 900 });
    await expect(controls).toBeVisible();
    const assistant = page.getByRole("region", { name: "AI Assistant pane", exact: true });
    await activateFloatingPane(assistant, "left");
    await assistant.getByRole("button", { name: "Close AI Assistant" }).click();
    await expect(assign).toHaveCSS("width", "36px");
    for (const button of [assign, edit, close]) await expect(button).toHaveCSS("height", "36px");
    await expect(filters).toHaveCount(0);
    await controls.click();
    const filterMenu = page.getByRole("menu", { name: "Timeline controls" });
    await expect(filterMenu.getByRole("radio", { name: "All Items", exact: true })).toBeVisible();
    await expect(filterMenu.getByRole("button", { name: "Edit", exact: true })).toHaveCount(0);
    await page.keyboard.press("Escape");

    // Inline controls keep their existing behavior and hit targets when compacted.
    await close.click();
    if (entity === "Case") {
      await expect(page.getByRole("dialog").getByText("Close Case", { exact: true }).first()).toBeVisible();
    } else {
      await expect(page.getByRole("menuitem", { name: "Mark as Done", exact: true })).toBeVisible();
    }
    await page.keyboard.press("Escape");

    await page.setViewportSize({ width: 320, height: 900 });
    await expect(edit).toHaveCount(0);
    await controls.click();
    await expect(filterMenu.getByRole("button", { name: "Edit", exact: true })).toBeVisible();
    await expect(filters).toBeVisible();
    await page.keyboard.press("Escape");

    status = closedStatus;
    await page.reload();
    const reopen = page.getByRole("button", { name: `Re-Open ${entity}`, exact: true });
    await controls.click();
    await expect(reopen).toBeVisible();
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 800, height: 900 });
    await expect(reopen).toHaveCSS("height", "36px");

    await page.setViewportSize({ width: 1980, height: 900 });
    const closedHeader = await measureHeaderCollapse(page, sample.human_id, [edit, assign, reopen]);
    for (const count of [2, 3]) await closedHeader.resizeToIcons(count);
    await page.route(new RegExp(`/api/v1/${resource}(?:\\?|$)`), (route) =>
      route.fulfill(jsonResponse({ ...emptyPage, items: [sample], total: 1, pages: 1 })),
    );
    await page.goto(`/${resource}`);
    await page.locator(`a[href="/${resource}/${sample.human_id}"]`).click();
    const view = page.getByRole("button", { name: `View ${entity}`, exact: true });
    const previewHeader = await measureHeaderCollapse(page, sample.human_id, [assign, view]);
    for (const count of [1, 2, 0]) await previewHeader.resizeToIcons(count);
  });
}

for (const { viewport, width, useAi } of [
  { viewport: "desktop", width: 1660, useAi: true },
  { viewport: "tablet", width: 800, useAi: true },
  { viewport: "mobile", width: 390, useAi: false },
]) {
  test(`alert escalation menu preserves the ${useAi ? "AI" : "manual"} flow on ${viewport}`, async ({ page }) => {
    await installProductionApiMocks(page);
    const recommendation = {
      id: 1,
      alert_id: 1,
      created_at: now,
      created_by: "tidemark_ai",
      status: "PENDING",
      disposition: "NEEDS_INVESTIGATION",
      request_escalate_to_case: true,
    };
    await page.route(/\/api\/v1\/alerts\/1(?:\?|$)/, (route) => route.fulfill(jsonResponse({
      ...sampleAlert,
      triage_recommendation: recommendation,
    })));
    const mutations: Record<string, unknown> = {};
    await page.route(/\/api\/v1\/alerts\/1\/(?:triage|triage-recommendation\/(?:accept|reject))$/, (route) => {
      const action = new URL(route.request().url()).pathname.split("/").pop()!;
      mutations[action] = route.request().postDataJSON();
      return route.fulfill(jsonResponse(
        action === "accept" ? { recommendation: { ...recommendation, status: "ACCEPTED" } }
          : action === "reject" ? { ...recommendation, status: "REJECTED" }
          : { ...sampleAlert, status: "ESCALATED" },
      ));
    });
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/alerts/ALT-0000001");
    const escalate = page.getByRole("button", { name: "Escalate to case", exact: true });
    const timelineControls = page.getByRole("button", { name: "Timeline controls" });
    if (viewport === "tablet") {
      await expect(page.getByRole("button", { name: "Unassigned", exact: true })).toHaveCSS("width", "36px");
      await expect(page.getByRole("button", { name: /^Close Alert/ })).toBeVisible();
      await expect(page.getByRole("button", { name: "Link to Case", exact: true })).toBeVisible();
      await expect(escalate).toBeVisible();
      const allItems = page.getByRole("radio", { name: "All Items", exact: true });
      await expect(allItems).toHaveCount(0);
      await timelineControls.click();
      await expect(allItems).toBeVisible();
      await expect(page.getByRole("menu").getByRole("button", { name: "Escalate to case", exact: true })).toHaveCount(0);
      await page.keyboard.press("Escape");
      await page.setViewportSize({ width: 390, height: 900 });
      await expect(escalate).toHaveCount(0);
      await timelineControls.click();
      await expect(escalate).toBeVisible();
      await page.keyboard.press("Escape");
      await page.setViewportSize({ width, height: 900 });
      await expect(escalate).toBeVisible();
    } else if (viewport === "mobile") {
      await expect(timelineControls).toBeVisible();
      await expect(escalate).toHaveCount(0);
      await timelineControls.click();
    }

    await escalate.press("Enter");
    const withAi = page.getByRole("menuitem", { name: "Use AI recommendation" });
    const manual = page.getByRole("menuitem", { name: "Escalate manually" });
    await expect(withAi).toHaveAccessibleName("Use AI recommendation Apply suggested changes");
    await expect(manual).toHaveAccessibleName("Escalate manually Reject the recommendation");
    expect(mutations).toEqual({});

    if (useAi) {
      await page.keyboard.press("Escape");
      await expect(escalate).toBeFocused();
      await escalate.press("ArrowDown");
      await expect(withAi).toBeFocused();
      await page.keyboard.press("Enter");
      await expect.poll(() => mutations).toEqual({
        accept: { apply_status: true, apply_priority: true, apply_assignee: true, apply_tags: true },
      });
    } else {
      await manual.click();
      const confirm = page.getByRole("dialog").getByRole("button", { name: "Reject Recommendation" });
      await expect(confirm).toBeDisabled();
      expect(mutations).toEqual({});
      await page.getByRole("dialog").getByRole("combobox").click();
      await page.getByRole("option", { name: "Prefer Manual Review" }).click();
      await confirm.click();
      await expect.poll(() => mutations).toEqual({
        reject: { category: "PREFER_MANUAL_REVIEW", reason: null },
        triage: {
          status: "ESCALATED",
          escalate_to_case: true,
          case_title: sampleAlert.title,
          case_description: sampleAlert.description,
        },
      });
    }
  });
}

test("wide chat history divider saves to its existing width preference", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.addInitScript(() => {
    localStorage.setItem("intercept-ai-pane-width", "512");
    if (localStorage.getItem("ai-chat-history-width") === null) {
      localStorage.setItem("ai-chat-history-width", "640");
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/ai-chat");
  const rail = page.getByRole("separator", { name: "Resize chat history" });
  await expect(rail).toHaveAttribute("aria-valuenow", "640");
  await rail.press("End");
  await expect(rail).toHaveAttribute("aria-valuenow", "706");
  expect(await page.evaluate(() => localStorage.getItem("ai-chat-history-width"))).toBe("706");
  expect(await page.evaluate(() => localStorage.getItem("intercept-ai-pane-width"))).toBe("512");
});

test("alert detail shows Analyst Context before the context preview at triage", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.addInitScript(() => {
    localStorage.setItem("intercept.theme-preference", "system");
    localStorage.setItem("intercept.alert-detail.triage-recommendation.expansion", "expanded");
  });
  const contextBody = "Scheduled maintenance is in progress.";
  const entry = {
    id: 17,
    body: `# Test context\n\n${contextBody}`,
    author: "admin",
    criteria: [],
    expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
  };
  await page.route(/\/api\/v1\/alerts\/1(?:\?|$)/, (route) => route.fulfill(jsonResponse({
    ...sampleAlert,
    context: { items: [entry], total_count: 1, omitted_count: 0 },
    triage_recommendation: {
      id: 1,
      alert_id: 1,
      created_at: now,
      created_by: "tidemark_ai",
      status: "PENDING",
      disposition: "NEEDS_INVESTIGATION",
      confidence: 0.8,
      request_escalate_to_case: true,
      suggested_status: "ESCALATED",
      suggested_priority: "MEDIUM",
      suggested_tags_add: ["network", "endpoint", "review"],
      reasoning_bullets: ["The evidence is incomplete.", "Check the daily baseline."],
      recommended_actions: [{ title: "Pull DNS telemetry" }, { title: "Compare with the daily baseline" }],
      applied_context_entries: [entry],
      context_snapshot_verified: true,
    },
  })));
  await page.setViewportSize({ width: 1696, height: 1000 });
  await page.goto("/alerts/ALT-0000001");
  const timeline = page.getByLabel("alert timeline content");
  const context = timeline.getByRole("region", { name: "Analyst Context" });
  const triage = timeline.getByText("AI Triage Recommendation", { exact: true });
  const top = (locator: Locator) => locator.evaluate((element) => element.getBoundingClientRect().top);

  for (const width of [1696, 1000, 390, 1920]) {
    const colorScheme = width === 390 || width === 1920 ? "light" : "dark";
    await page.emulateMedia({ colorScheme });
    await page.setViewportSize({ width, height: 1000 });
    await expect(page.locator("html")).toHaveAttribute("data-theme", colorScheme);
    await expect(context).toBeVisible();
    await expect(triage).toBeVisible();
    expect(await top(context)).toBeLessThan(await top(triage));
    await expect(context.getByRole("link", { name: "View all context" })).toHaveCount(0);
    await expect(context.getByText(contextBody, { exact: true })).toHaveCount(1);
    await expect(context.getByText("Matched Context", { exact: true })).toHaveCount(0);
    await expect(context.getByRole("button", { name: /Expires in 7 days/ })).toBeVisible();
    const triageCard = timeline.getByRole("region", { name: "AI Triage Recommendation" });
    const savedContextRow = triageCard.getByRole("button", { name: /^Context at Triage/ });
    await expect(savedContextRow).toContainText(contextBody);
    await expect(triageCard.getByText("1 context entry supplied", { exact: true })).toBeVisible();
    await expect(triageCard.getByRole("progressbar")).toHaveCount(0);
    const triageHeader = triageCard.locator("header");
    const confidence = triageHeader.getByText("80%", { exact: true });
    const disposition = triageHeader.getByText("Needs Investigation", { exact: true });
    const action = triageCard.getByText("Escalate to case and investigate", { exact: true }).locator("..");
    await expect(confidence).toBeVisible();
    await expect(disposition).toBeVisible();
    await expect(context.getByText("1 active", { exact: true }).locator("..")).toHaveCSS("height", "20px");
    await expect(disposition.locator("..")).toHaveCSS("height", "20px");
    await expect(triageHeader.getByText("Pending Review", { exact: true })).toHaveCount(0);
    await expect(action).toBeVisible();
    await expect(action).toHaveCSS("border-top-width", "1px");
    await expect(action).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    expect(await top(action)).toBeGreaterThan(await top(disposition));
    // Measure both in the same frame because the narrow detail pane animates as a unit.
    const widthDelta = await action.evaluate((element) => {
      const header = element.closest("section")?.querySelector("header");
      if (!header) throw new Error("Expected the triage header");
      return element.getBoundingClientRect().width - header.getBoundingClientRect().width;
    });
    expect(widthDelta).toBeCloseTo(0, 0);
    if (width === 1920) {
      expect(Math.abs(await top(confidence) - await top(triage))).toBeLessThan(8);
      expect(Math.abs(await top(disposition) - await top(triage))).toBeLessThan(8);
      const contextToChevron = await triageHeader.getByText("1 context entry supplied", { exact: true }).evaluate((element) => {
        const chevron = element.closest("header")?.querySelector("button[aria-expanded]");
        if (!chevron) throw new Error("Expected the triage collapse button");
        return chevron.getBoundingClientRect().left - element.getBoundingClientRect().right;
      });
      expect(contextToChevron).toBeGreaterThanOrEqual(0);
      expect(contextToChevron).toBeLessThanOrEqual(16);
    }
    const reasonRow = triageCard.getByRole("button", { name: /^Reasoning/ });
    const changesRow = triageCard.getByRole("button", { name: /^Recommended Changes/ });
    const taskRow = triageCard.getByRole("button", { name: /^Recommended Tasks/ });
    for (const row of [reasonRow, changesRow, taskRow]) await expect(row).toHaveAttribute("aria-expanded", "false");
    const firstTask = taskRow.getByText("Pull DNS telemetry", { exact: true });
    const taskLabel = taskRow.getByText("Recommended Tasks", { exact: true });
    await expect(firstTask).toBeVisible();
    const accept = triageCard.getByRole("button", { name: "Accept Recommendation" });
    const reject = triageCard.getByRole("button", { name: "Reject", exact: true });
    const warningColor = colorScheme === "dark" ? "rgb(255, 118, 13)" : "rgb(160, 52, 12)";
    await expect(accept).toHaveCSS("height", "32px");
    await expect(reject).toHaveCSS("border-top-color", warningColor);
    await expect(reject.getByText("Reject", { exact: true })).toHaveCSS("color", warningColor);
    if (width === 390) expect(await top(firstTask)).toBeGreaterThan(await top(taskLabel));
    if (width === 1000 || width === 390) {
      const expandedTextColor = await action.evaluate((element) => getComputedStyle(element).color);
      await triageHeader.getByRole("button", { name: "Collapse triage recommendation" }).click();
      await expect(action).toBeVisible();
      await expect(triageCard.getByText("The evidence is incomplete.", { exact: true }).filter({ visible: true })).toHaveCount(1);
      await expect(accept).toHaveCSS("height", "32px");
      await expect(action).toHaveCSS("height", "32px");
      await expect(action).toHaveCSS("border-top-width", "0px");
      await expect(action).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
      await expect(action).not.toHaveCSS("color", expandedTextColor);
      await expect(reject).toHaveCSS("border-top-color", warningColor);
      await expect(reasonRow).toHaveCount(0);
      await triageHeader.getByRole("button", { name: "Expand triage recommendation" }).click();
    }
    if (width === 1920) {
      expect(Math.abs(await top(firstTask) - await top(taskLabel))).toBeLessThan(5);
      await taskRow.press("Space");
      await expect(taskRow).toHaveAttribute("aria-expanded", "true");
      await expect(triageCard.getByText("Compare with the daily baseline", { exact: true })).toBeVisible();
      await expect(reasonRow).toHaveAttribute("aria-expanded", "false");
      await expect(changesRow).toHaveAttribute("aria-expanded", "false");
      await triageCard.getByRole("button", { name: "Reject", exact: true }).click();
      const rejection = page.getByRole("dialog");
      await expect(rejection.getByText("Select the reason for rejecting this AI triage recommendation.")).toBeVisible();
      await rejection.getByRole("button", { name: "Cancel" }).click();
      await expect(rejection).toHaveCount(0);
    }
    const title = context.getByRole("heading", { name: "Test context" });
    const scope = context.getByText("Global", { exact: true });
    if (width === 1920) expect(Math.abs(await top(title) - await top(scope))).toBeLessThan(10);
    if (width === 390) expect(await top(scope)).toBeGreaterThan(await top(context.getByText(contextBody)));
  }
});

test("alert card expansion preferences are independent and follow the analyst across alerts and reloads", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.route("**/api/v1/features", (route) => route.fulfill(jsonResponse({ ai_triage_enabled: true })));
  let rerunQueued = false;
  await page.route("**/api/v1/alerts/2/triage-recommendation/enqueue", (route) => {
    expect(route.request().postDataJSON()).toEqual({ expected_recommendation_created_at: now });
    rerunQueued = true;
    return route.fulfill(jsonResponse({ status: "QUEUED" }));
  });
  await page.route(/\/api\/v1\/alerts\/[12](?:\?|$)/, (route) => {
    const alert = new URL(route.request().url()).pathname.endsWith("/1") ? sampleAlert : secondAlert;
    const entry = { id: 17, body: `# Test context\n\nContext for ${alert.human_id}.`, author: "admin", criteria: [] };
    return route.fulfill(jsonResponse({
      ...alert,
      context: { items: [entry], total_count: 1 },
      triage_context_changed: alert.id === secondAlert.id,
      triage_recommendation: {
        id: alert.id,
        alert_id: alert.id,
        created_at: now,
        created_by: "tidemark_ai",
        status: alert.id === secondAlert.id && rerunQueued ? "QUEUED" : "PENDING",
        disposition: alert.id === secondAlert.id ? "BENIGN" : "NEEDS_INVESTIGATION",
        confidence: 0.8,
        request_escalate_to_case: true,
        suggested_status: "ESCALATED",
        context_snapshot_verified: true,
        applied_context_entries: [{ ...entry, body: "Saved context from triage" }],
        reasoning_bullets: ["**More evidence** is needed. See the [triage guide](https://example.com).", "Check the daily baseline."],
      },
    }));
  });

  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto(`/alerts/${sampleAlert.human_id}`);
  const timeline = page.getByLabel("alert timeline content");
  const context = timeline.getByRole("region", { name: "Analyst Context", exact: true });
  const triage = timeline.getByRole("region", { name: "AI Triage Recommendation", exact: true });
  const collapseContext = context.getByRole("button", { name: "Collapse analyst context" });
  const expandContext = context.getByRole("button", { name: "Expand analyst context" });
  const collapseTriage = triage.getByRole("button", { name: "Collapse triage recommendation" });
  const expandTriage = triage.getByRole("button", { name: "Expand triage recommendation" });
  const accept = triage.getByRole("button", { name: "Accept Recommendation" });
  const reject = triage.getByRole("button", { name: "Reject", exact: true });
  const rerun = triage.getByRole("button", { name: "Rerun AI Triage" });
  const expectSeparatedReviewActions = async () => {
    await expect(rerun).toHaveCSS("height", "32px");
    const triageBounds = (await triage.boundingBox())!;
    const header = (await triage.locator("header").boundingBox())!;
    const rerunBounds = (await rerun.boundingBox())!;
    const rejectBounds = (await reject.boundingBox())!;
    const acceptBounds = (await accept.boundingBox())!;
    expect(rerunBounds.x).toBeCloseTo(header.x, 0);
    expect(acceptBounds.x + acceptBounds.width).toBeCloseTo(header.x + header.width, 0);
    expect(rejectBounds.x - (rerunBounds.x + rerunBounds.width)).toBeGreaterThan(8);
    expect(acceptBounds.x - (rejectBounds.x + rejectBounds.width)).toBeCloseTo(8, 0);
    for (const button of [rerunBounds, rejectBounds, acceptBounds]) {
      expect(triageBounds.y + triageBounds.height - (button.y + button.height))
        .toBeCloseTo(header.y - triageBounds.y, 0);
    }
  };
  const escalate = page.getByRole("button", { name: /^Escalate to Case$/i });
  const action = triage.getByText("Escalate to case and investigate", { exact: true }).locator("..");
  const openAlert = async (alert: typeof sampleAlert) => {
    await page.getByRole("link", { name: new RegExp(alert.title) }).click();
    await expect(page).toHaveURL(new RegExp(`/alerts/${alert.human_id}$`));
    await expect(context.getByText(new RegExp(`Context for ${alert.human_id}`))).toBeVisible();
  };

  await expect(expandTriage).toHaveAttribute("aria-expanded", "false");
  await expandTriage.click();
  await expect(collapseTriage).toHaveAttribute("aria-expanded", "true");
  await expect(escalate).toHaveAttribute("aria-haspopup", "menu");
  await expect(triage.getByText("Context changed since triage")).toHaveCount(0);
  await expectSeparatedReviewActions();
  const changes = triage.getByRole("button", { name: /^Recommended Changes/ });
  await expect(changes).toBeInViewport({ ratio: 1 });
  await collapseContext.click();
  await openAlert(secondAlert);
  await expect(expandContext).toHaveAttribute("aria-expanded", "false");
  await expect(triage.getByText("Dismiss alert", { exact: true })).toBeVisible();
  await expect(escalate).not.toHaveAttribute("aria-haspopup");
  await expect(triage.getByText("Context changed since triage")).toBeVisible();
  await expect(accept).toBeVisible();
  await collapseTriage.press("Space");
  await expect(expandTriage).toBeFocused();
  await expect(triage.getByText("Dismiss alert", { exact: true })).toBeVisible();
  await expect(triage.getByText("Context changed since triage")).toBeVisible();
  await expectSeparatedReviewActions();
  await openAlert(sampleAlert);
  await page.reload();
  await expect(expandContext).toHaveAttribute("aria-expanded", "false");
  await expect(expandTriage).toHaveAttribute("aria-expanded", "false");
  await expect(action).toBeVisible();
  const reasonPreview = triage.getByText("More evidence is needed. See the triage guide.", { exact: true }).filter({ visible: true });
  await expect(reasonPreview).toBeVisible();
  await expect(reasonPreview.locator("strong, a")).toHaveCount(0);
  const previewBounds = (await reasonPreview.boundingBox())!;
  await expect(accept).toHaveCSS("height", "32px");
  await expect(reject).toHaveCSS("height", "32px");
  await expect(action).toHaveCSS("height", "32px");
  const buttonLabelSize = await accept.getByText("Accept Recommendation", { exact: true })
    .evaluate((label) => getComputedStyle(label).fontSize);
  await expect(action).toHaveCSS("font-size", buttonLabelSize);
  await expect(triage.getByRole("button", { name: /^Reasoning/ })).toHaveCount(0);
  const bannerBounds = (await action.boundingBox())!;
  const acceptBounds = (await accept.boundingBox())!;
  const headerBounds = (await triage.locator("header").boundingBox())!;
  expect(previewBounds.y).toBeGreaterThanOrEqual(headerBounds.y + headerBounds.height);
  expect(bannerBounds.y).toBeGreaterThanOrEqual(previewBounds.y + previewBounds.height);
  expect(acceptBounds.y).toBeGreaterThanOrEqual(bannerBounds.y + bannerBounds.height);
  await expectSeparatedReviewActions();

  await expandTriage.click();
  await openAlert(secondAlert);
  await expect(expandContext).toHaveAttribute("aria-expanded", "false");
  await expect(accept).toHaveCSS("height", "32px");
  await expandContext.click();
  await page.reload();
  await expect(collapseContext).toHaveAttribute("aria-expanded", "true");
  await expect(collapseTriage).toHaveAttribute("aria-expanded", "true");
  const savedContext = triage.getByRole("button", { name: /^Context at Triage/ });
  const reasoning = triage.getByRole("button", { name: /^Reasoning/ });
  expect((await savedContext.boundingBox())!.y).toBeLessThan((await reasoning.boundingBox())!.y);
  await savedContext.click();
  const savedEntry = triage.getByRole("listitem").filter({ hasText: "Saved context from triage" });
  const savedBody = savedEntry.getByText("Saved context from triage", { exact: true });
  const savedAuthor = savedEntry.getByText("admin", { exact: true });
  await expect(savedBody).toBeVisible();
  const bodyBounds = (await savedBody.boundingBox())!;
  expect((await savedAuthor.boundingBox())!.x).toBeGreaterThanOrEqual(bodyBounds.x + bodyBounds.width + 8);
  await expectSeparatedReviewActions();
  await rerun.click();
  await expect(timeline.getByText("AI Triage In Progress")).toBeVisible();
});

const floatingQueues = [
  { entity: "Alert", resource: "alerts", sample: sampleAlert, prefix: "ALT" },
  { entity: "Case", resource: "cases", sample: sampleCase, prefix: "CAS" },
  { entity: "Task", resource: "tasks", sample: sampleTask, prefix: "TSK" },
] as const;

for (const { entity, resource, sample } of floatingQueues) {
  test(`${resource} searches the current queue and highlights matching list and detail text`, async ({ page }) => {
    await installProductionApiMocks(page);
    const oldRow = { ...sample, title: "Normal queue item" };
    const matchingRow = { ...sample, title: "Quartz detection", tags: ["quartz-tag"] };
    const detail = {
      ...matchingRow,
      description: "**Quartz** was observed",
      timeline_items: {
        "note-1": { id: "note-1", type: "note", timestamp: now, created_at: now, description: "Review **Quartz** in the note" },
      },
    };
    await page.route(new RegExp(`/api/v1/${resource}(?:\\?|$)`), (route) =>
      route.fulfill(jsonResponse({ ...emptyPage, items: [oldRow], total: 1, pages: 1 })));
    await page.route(new RegExp(`/api/v1/${resource}/(?:1|${sample.human_id})(?:\\?|$)`), (route) =>
      route.fulfill(jsonResponse(detail)));
    await page.route("**/api/v1/search/queue?*", (route) =>
      route.fulfill(jsonResponse({ results: [matchingRow], total: 1, skip: 0, limit: 50 })));
    await page.addInitScript(() => localStorage.setItem("intercept-ai-pane-width", "320"));
    await page.emulateMedia({ colorScheme: resource === "cases" ? "light" : "dark" });
    await page.setViewportSize({ width: 1372, height: 900 });
    const initialFilters = "assignee=__unassigned__%2Canalyst&include_tags=quartz-tag&exclude_tags=noise&sort_by=updated_at&sort_order=asc&page=2";
    await page.goto(`/${resource}?${initialFilters}`);

    const search = page.getByRole("textbox", { name: "Search this queue" });
    const filter = page.getByRole("button", { name: /^Filters/ });
    const order = page.getByRole("button", { name: /^Sort/ });
    const checkbox = page.getByRole("checkbox", { name: `Select ${sample.human_id}` });
    await checkbox.press("Space");
    await expect(checkbox).toBeChecked();
    const [inputBox, filterBox, sortBox] = await Promise.all([search.boundingBox(), filter.boundingBox(), order.boundingBox()]);
    expect(inputBox!.x).toBeGreaterThan(filterBox!.x + filterBox!.width);
    expect(inputBox!.x + inputBox!.width).toBeLessThan(sortBox!.x);

    const request = page.waitForRequest((req) => new URL(req.url()).pathname === "/api/v1/search/queue");
    await search.fill("Quartz");
    const args = new URL((await request).url()).searchParams;
    expect(args.get("entity_type")).toBe(entity.toLowerCase());
    expect(args.getAll("assignee").sort()).toEqual(["__unassigned__", "analyst"]);
    expect(args.getAll("status")).toEqual([sample.status, "IN_PROGRESS"]);
    expect(args.get("include_tags")).toBe("quartz-tag");
    expect(args.get("exclude_tags")).toBe("noise");
    expect(args.get("sort_by")).toBe("updated_at");
    expect(args.get("sort_order")).toBe("asc");
    expect(args.get("skip")).toBe("0");
    expect(args.has("start_date")).toBe(false);
    const row = page.locator(`a[href^="/${resource}/${sample.human_id}"]`);
    await expect(row.locator("[data-search-highlight]").first()).toHaveText("Quartz");
    await expect(checkbox).not.toBeChecked();
    await expect(row).not.toContainText("observed");

    await page.setViewportSize({ width: 390, height: 900 });
    await row.click();
    const timeline = page.getByLabel(`${entity.toLowerCase()} timeline content`);
    await expect(timeline.locator("[data-search-highlight]").filter({ hasText: "Quartz" }).first()).toBeVisible();
    await expect(timeline.locator("strong [data-search-highlight]").filter({ hasText: "Quartz" })).toHaveCount(2);
    await expect(page).toHaveURL((url) => url.searchParams.get("search") === "Quartz");
    await page.getByRole("button", { name: "Back to list", exact: true }).click();
    await expect(search).toHaveValue("Quartz");
    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page).toHaveURL((url) => !url.searchParams.has("search") && url.searchParams.get("sort_by") === "updated_at");
    await expect(row).toHaveText(/Normal queue item/);
    await expect(row.locator("[data-search-highlight]")).toHaveCount(0);
  });
}

test("a late queue search cannot replace newer results", async ({ page }) => {
  await installProductionApiMocks(page);
  let releaseSlow!: () => void;
  const slow = new Promise<void>((resolve) => { releaseSlow = resolve; });
  await page.route("**/api/v1/search/queue?*", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q");
    if (query === "older") await slow;
    await route.fulfill(jsonResponse({
      results: [{ ...sampleAlert, title: query === "older" ? "Older answer" : "Newest answer" }],
      total: 1, skip: 0, limit: 50,
    })).catch(() => { /* A superseded request can already be cancelled. */ });
  });
  await page.goto("/alerts");
  try {
    const search = page.getByRole("textbox", { name: "Search this queue" });
    const previous = page.waitForRequest((req) => new URL(req.url()).searchParams.get("q") === "older");
    await search.fill("older");
    await previous;
    await expect(page.getByRole("status").filter({ hasText: "Searching…" })).toBeVisible();
    await search.fill("newest");
    await expect(page.getByRole("link", { name: /Newest answer/ })).toBeVisible();
  } finally {
    releaseSlow();
  }
  await expect(page.getByRole("link", { name: /Newest answer/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Older answer/ })).toHaveCount(0);
});

test("a failed queue search can retry without showing unfiltered rows", async ({ page }) => {
  await installProductionApiMocks(page);
  let attempts = 0;
  await page.route("**/api/v1/search/queue?*", (route) => {
    attempts++;
    return route.fulfill(attempts === 1
      ? { status: 503, json: { detail: "Temporarily unavailable" } }
      : jsonResponse({ results: [], total: 0, skip: 0, limit: 50 }));
  });
  await page.goto("/alerts?search=no-match");
  await expect(page.getByRole("alert")).toContainText("Couldn’t search this queue.");
  await expect(page.getByRole("link", { name: /Production smoke alert/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("No matching results", { exact: true })).toBeVisible();
  expect(attempts).toBe(2);
});

async function installFloatingQueueMocks(page: Page, { resource, sample, prefix }: typeof floatingQueues[number]) {
  await installProductionApiMocks(page);
  const second = { ...sample, id: 2, human_id: `${prefix}-0000002`, title: `Second ${resource} preview` };
  await page.route(new RegExp(`/api/v1/${resource}(?:\\?|$)`), (route) =>
    route.fulfill(jsonResponse({ ...emptyPage, items: [sample, second], total: 2, pages: 1 })),
  );
  await page.route(new RegExp(`/api/v1/${resource}/2(?:\\?|$)`), (route) =>
    route.fulfill(jsonResponse(second)),
  );
  return second;
}

const paneScale = (pane: Locator) => pane.evaluate((el) => el.getBoundingClientRect().width / el.clientWidth);

const paneActivator = (pane: Locator) => pane.getByRole("button", { name: /^Bring .* to front$/ });
async function activateFloatingPane(pane: Locator, edge: "left" | "right") {
  const button = paneActivator(pane);
  const bounds = (await button.boundingBox())!;
  await button.click({ position: { x: edge === "left" ? 30 : bounds.width - 30, y: 100 } });
}

test("floating panes require 1000 ms of continuous hover before changing the stack", async ({ page }) => {
  await installFloatingQueueMocks(page, floatingQueues[0]);
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.goto("/alerts/ALT-0000001");
  const list = page.getByRole("region", { name: "Alert list", exact: true });
  const button = paneActivator(list);
  await expect(button).toBeVisible();
  const edge = (await button.boundingBox())!;
  const now = new Date();
  await page.clock.install({ time: now });
  await page.clock.pauseAt(new Date(now.getTime() + 60_000));

  const enter = () => page.mouse.move(edge.x + 30, edge.y + 100);
  await enter();
  await page.clock.runFor(600);
  await page.mouse.move(0, 0);
  await page.clock.runFor(1000);
  await expect(button).toBeVisible();

  await enter();
  await page.clock.runFor(999);
  await expect(button).toBeVisible();
  await page.clock.runFor(1);
  await expect(button).toHaveCount(0);
});

test("the case timeline fits narrow screens with wide emails and attachments", async ({ page }) => {
  const longLine = "mailbody".repeat(25);
  const attachmentName = `${"attachment".repeat(16)}.pdf`;
  await installProductionApiMocks(page);
  await page.route("**/api/v1/cases/1?*", (route) => route.fulfill(jsonResponse({
    ...sampleCase,
    timeline_items: {
      email: {
        id: "email", type: "email", timestamp: now, created_at: now,
        subject: "Example email", sender: "sender@example.com", recipient: "recipient@example.com",
        message_id: `<${"messageid".repeat(15)}@example.com>`,
        description: `    ${longLine}\n      Indented second line`,
      },
      attachment: {
        id: "attachment", type: "attachment", timestamp: now, created_at: now,
        file_name: attachmentName, mime_type: "application/pdf", file_size: 1024,
      },
    },
  })));
  await page.setViewportSize({ width: 468, height: 900 });
  await page.goto("/cases/CAS-0000001");

  const timeline = page.getByLabel("case timeline content");
  const preformatted = timeline.locator("pre").filter({ hasText: longLine });
  await expect(timeline.getByText("Example email", { exact: true })).toBeVisible();
  await expect(timeline.getByText(attachmentName, { exact: true }).first()).toBeVisible();
  await expect(preformatted).toBeVisible();
  expect(await preformatted.textContent()).toContain(`${longLine}\n  Indented second line`);
  await page.evaluate(() => document.fonts.ready);

  for (const width of [468, 360, 1000, 1600, 2400]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => timeline.evaluate((node) => node.scrollWidth - node.clientWidth), {
      message: `Timeline should not scroll horizontally at ${width}px`,
    }).toBeLessThanOrEqual(1);
    expect(await preformatted.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1);
  }
});

for (const { entity, path } of [
  { entity: "Case", path: "/cases/CAS-0000001" },
  { entity: "Task", path: "/tasks/TSK-0000001" },
]) {
  test(`the narrow ${entity} detail and AI assistant float over each other`, async ({ page }) => {
    await installProductionApiMocks(page);
    await page.setViewportSize({ width: 1000, height: 900 });
    await page.goto(path);

    const assistant = page.getByRole("region", { name: "AI Assistant pane", exact: true });
    const detail = page.getByRole("region", { name: `${entity} detail`, exact: true });
    const rail = page.getByRole("separator", { name: "Resize assistant pane" });
    const timeline = page.getByLabel(`${entity.toLowerCase()} timeline content`);
    await expect(timeline).toBeVisible();
    await expect(rail).toHaveCount(0);
    await expect.poll(() => paneScale(assistant)).toBeCloseTo(0.98, 2);
    await expect.poll(() => paneScale(detail)).toBeCloseTo(1, 2);

    const timelineWidth = await detail.evaluate((element) => element.clientWidth);
    await expect(assistant.getByRole("textbox", { name: /Ask me anything/ })).toHaveCount(0);
    await activateFloatingPane(assistant, "left");
    await expect.poll(() => paneScale(assistant)).toBeCloseTo(1, 2);
    await expect.poll(() => paneScale(detail)).toBeCloseTo(0.98, 2);
    expect(await detail.evaluate((element) => element.clientWidth)).toBe(timelineWidth);
    await activateFloatingPane(detail, "right");
    await expect.poll(() => paneScale(detail)).toBeCloseTo(1, 2);

    await paneActivator(assistant).focus();
    await expect.poll(() => paneScale(assistant)).toBeCloseTo(0.98, 2);
    await page.keyboard.press("Enter");
    await expect(assistant).toBeFocused();
    await expect.poll(() => paneScale(assistant)).toBeCloseTo(1, 2);
    await page.setViewportSize({ width: 800, height: 900 });
    await expect(assistant).toBeVisible();
    await expect(detail).toBeVisible();

    await page.setViewportSize({ width: 1600, height: 900 });
    await expect(rail).toBeVisible();
    await expect(assistant).toHaveCount(0);
    await expect(timeline).toBeVisible();

    await page.setViewportSize({ width: 700, height: 900 });
    await page.reload();
    await expect(timeline).toBeVisible();
    await expect(assistant).toHaveCount(0);
    await expect(rail).toHaveCount(0);
  });
}

for (const queue of floatingQueues) {
  const { entity, resource, sample, prefix } = queue;
  test(`the ${resource} queue fits at the minimum split width`, async ({ page }) => {
    const title = `${sample.title}: ${"long-title".repeat(12)}`;
    const assignee = "on-call-investigator-with-a-long-username";
    const tags = ["needs-review", "tag-with-an-unbroken-identifier".repeat(3), "follow-up"];
    await installFloatingQueueMocks(page, {
      ...queue, sample: { ...sample, title, tags, assignee },
    });
    await page.emulateMedia({ colorScheme: resource === "cases" ? "light" : "dark" });
    await page.addInitScript(() => localStorage.setItem("intercept-ai-pane-width", "320"));
    await page.setViewportSize({ width: 1372, height: 900 });
    await page.goto(`/${resource}`);

    const link = page.getByRole("link", { name: new RegExp(sample.title) });
    const rail = page.getByRole("separator", { name: `Resize ${entity.toLowerCase()} list` });
    await expect(rail).toHaveAttribute("aria-valuenow", "320");
    const scrollArea = page.getByRole("checkbox", { name: `Select visible ${resource}` })
      .locator("xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' overflow-auto ')][1]");
    const status = link.locator('[data-queue-indicator="status"]');
    const priority = link.locator('[data-queue-indicator="priority"]');
    await expect(status).toHaveText(resource === "tasks" ? "TDO" : "NEW", { useInnerText: true });
    await expect(priority).toHaveText("P4", { useInnerText: true });
    await expect(link.getByTitle(title, { exact: true })).toBeVisible();
    await expect(link.getByTitle(assignee, { exact: true })).toBeVisible();
    await expect(link.getByTitle(/^2026-01-01/)).toBeVisible();
    const rowCheckbox = page.getByRole("checkbox", { name: `Select ${sample.human_id}` });
    await rowCheckbox.press("Space");
    await expect(rowCheckbox).toBeChecked();
    await rowCheckbox.press("Space");
    await expect(rowCheckbox).not.toBeChecked();

    const expectQueueToFit = async () => {
      await expect.poll(() => scrollArea.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
      const cardBounds = (await link.boundingBox())!;
      for (const item of [status, priority]) {
        const bounds = (await item.boundingBox({ timeout: 5000 }))!;
        expect(bounds.x + bounds.width).toBeLessThan(cardBounds.x + cardBounds.width);
      }
    };

    await expectQueueToFit();
    const lastTagAction = link.getByRole("button", { name: "Include follow-up", exact: true });
    const lastTagBounds = (await lastTagAction.boundingBox({ timeout: 5000 }))!;
    const cardBounds = (await link.boundingBox())!;
    expect(lastTagBounds.x + lastTagBounds.width).toBeLessThan(cardBounds.x + cardBounds.width);

    for (const width of [360, 800, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      if (width === 1920) await rail.press("End");
      await expectQueueToFit();
    }
  });

  test(`the ${resource} placeholder logo fits the exposed strip only in floating mode`, async ({ page }) => {
    await installFloatingQueueMocks(page, queue);
    await page.setViewportSize({ width: 1131, height: 1253 });
    await page.goto(`/${resource}`);

    const list = page.getByRole("region", { name: `${entity} list`, exact: true });
    const detail = page.getByRole("region", { name: `${entity} detail`, exact: true });
    const logo = page.getByRole("img", { name: "Intercept Logo" });
    for (const viewport of [{ width: 1131, height: 1253 }, { width: 800, height: 480 }]) {
      await page.setViewportSize(viewport);
      await expect(logo).toHaveCSS("rotate", "90deg");
      await expect.poll(async () => {
        const [image, queuePane, detailPane] = await Promise.all([
          logo.boundingBox(), list.boundingBox(), detail.boundingBox(),
        ]);
        return !!(image && queuePane && detailPane && image.height > image.width &&
          image.x > queuePane.x + queuePane.width && image.x + image.width < detailPane.x + detailPane.width &&
          image.y > detailPane.y && image.y + image.height < detailPane.y + detailPane.height);
      }).toBe(true);
    }

    await page.setViewportSize({ width: 1920, height: 900 });
    await expect(logo).toHaveCSS("rotate", "none");
    await page.setViewportSize({ width: 700, height: 900 });
    await expect(logo).toHaveCount(0);
  });

  test(`narrow ${resource} view keeps the queue and detail reachable`, async ({ page }) => {
    const second = await installFloatingQueueMocks(page, queue);
    const timeline = page.getByLabel(`${entity.toLowerCase()} timeline content`);
    const itemLinks = page.locator(`a[href^="/${resource}/${prefix}-"]`);
    await page.setViewportSize({ width: 1000, height: 900 });
    await page.goto(`/${resource}?sort_by=updated_at`);

    const list = page.getByRole("region", { name: `${entity} list`, exact: true });
    const detail = page.getByRole("region", { name: `${entity} detail`, exact: true });
    const placeholder = detail.getByRole("img", { name: "Intercept Logo" });
    await expect(placeholder).toBeVisible();
    await expect.poll(() => paneScale(detail)).toBeCloseTo(0.98, 2);
    await expect.poll(() => paneScale(list)).toBeCloseTo(1, 2);
    const placeholderBounds = (await detail.boundingBox())!;
    await detail.hover({ position: { x: placeholderBounds.width - 30, y: 100 } });
    expect(await paneScale(detail)).toBeCloseTo(0.98, 2);
    const initialQueue = (await list.elementHandle())!;
    const dimensions = await list.evaluate((node) => [node.clientWidth, node.clientHeight]);

    await itemLinks.first().click();
    await expect(detail).toBeFocused();
    await expect.poll(() => paneScale(list)).toBeCloseTo(0.98, 2);
    await expect(placeholder).toHaveCount(0);
    expect(await list.evaluate((node, initial) => node === initial, initialQueue)).toBe(true);
    expect(await list.evaluate((node) => [node.clientWidth, node.clientHeight])).toEqual(dimensions);
    await initialQueue.dispose();

    // Clicking either exposed edge brings that pane forward immediately.
    await activateFloatingPane(list, "left");
    await expect.poll(() => paneScale(list)).toBeCloseTo(1, 2);
    await expect.poll(() => paneScale(detail)).toBeCloseTo(0.98, 2);
    await activateFloatingPane(detail, "right");
    await expect.poll(() => paneScale(detail)).toBeCloseTo(1, 2);

    await paneActivator(list).press("Space");
    await expect(list).toBeFocused();
    await list.getByRole("link", { name: new RegExp(second.title) }).focus();
    await expect.poll(() => paneScale(list)).toBeCloseTo(1, 2);
    await page.keyboard.press("Enter");
    const previewPath = resource === "alerts" ? `/alerts/${second.human_id}` : `/${resource}`;
    await expect(page).toHaveURL((url) => url.pathname === previewPath && url.searchParams.get("sort_by") === "updated_at");
    await expect(detail).toBeFocused();
    await expect(detail.getByText(second.title, { exact: true })).toBeVisible();

    await page.setViewportSize({ width: 800, height: 900 });
    await expect(list).toBeVisible();
    await expect(detail).toBeVisible();

    if (resource !== "alerts") {
      // The floating preview doesn't replace the full-detail route.
      await detail.getByRole("button", { name: `View ${entity}`, exact: true }).click();
      await expect(page).toHaveURL((url) => url.pathname === `/${resource}/${second.human_id}`);
      await page.goto(`/${resource}`);
      await itemLinks.first().dblclick();
      await expect(page).toHaveURL((url) => url.pathname === `/${resource}/${sample.human_id}`);
      await page.setViewportSize({ width: 700, height: 900 });
      await page.goto(`/${resource}`);
      await itemLinks.first().click();
      await expect(page).toHaveURL((url) => url.pathname === `/${resource}/${sample.human_id}`);
      await expect(timeline).toBeVisible();
      await expect(list).toHaveCount(0);
      return;
    }

    await page.setViewportSize({ width: 700, height: 900 });
    await expect(list).toHaveCount(0);
    await expect(itemLinks).toHaveCount(0);
    await expect(timeline).toBeVisible();

    await page.setViewportSize({ width: 1920, height: 900 });
    await expect(itemLinks.first()).toBeVisible();
    await expect(timeline).toBeVisible();
    await expect(list).toHaveCount(0);
  });

  test(`the narrow ${resource} overlay can bring the selection summary and list to the front`, async ({ page }) => {
    await installFloatingQueueMocks(page, queue);
    await page.setViewportSize({ width: 1000, height: 900 });
    await page.goto(`/${resource}`);
    await page.getByRole("checkbox", { name: `Select visible ${resource}` }).press("Space");
    const list = page.getByRole("region", { name: `${entity} list`, exact: true });
    const summary = page.getByRole("region", { name: "Selection summary" });
    await list.getByRole("button", { name: "Review selection" }).click();
    await expect(page.getByRole("region", { name: `${entity} detail`, exact: true })).toBeFocused();
    await expect(summary.getByRole("heading")).toHaveText(`2 ${resource} selected`);
    await summary.getByRole("button", { name: "Back to list" }).click();
    await expect(list).toBeFocused();
    await expect(list.getByRole("checkbox", { name: `Select visible ${resource}` })).toBeChecked();
  });
}

test.describe("floating queue on touch", () => {
  test.use({ hasTouch: true });

  test("the exposed case queue edge brings the list back", async ({ page }) => {
    await installFloatingQueueMocks(page, floatingQueues[1]);
    await page.setViewportSize({ width: 800, height: 900 });
    await page.goto("/cases");
    await page.getByRole("link", { name: new RegExp(sampleCase.title) }).tap();
    const list = page.getByRole("region", { name: "Case list", exact: true });
    await expect.poll(() => paneScale(list)).toBeCloseTo(0.98, 2);
    await paneActivator(list).tap({ position: { x: 30, y: 100 } });
    await expect.poll(() => paneScale(list)).toBeCloseTo(1, 2);
  });
});

test("alert Bulk Action sends one update with status, assignee, suggested tag and note", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.route("**/api/v1/features", (route) => route.fulfill(jsonResponse({
    case_closure_recommended_tags: ["Reviewed"],
  })));
  const updates: unknown[] = [];
  await page.route("**/api/v1/alerts/bulk-actions", async (route) => {
    updates.push(route.request().postDataJSON());
    await route.fulfill(jsonResponse({ updated_count: 2, updated_alerts: [sampleAlert, secondAlert] }));
  });
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto("/alerts");
  await page.getByRole("checkbox", { name: "Select visible alerts" }).press("Space");
  const summary = page.getByRole("region", { name: "Selection summary" });
  await expect(summary.getByRole("heading")).toHaveText("2 alerts selected");
  await expect(summary.getByRole("listitem").filter({ hasText: "ALT-0000002" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Duplicate", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Bulk", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "Bulk Action" });
  const apply = dialog.getByRole("button", { name: "Apply" });
  await expect(apply).toBeDisabled();
  await dialog.getByRole("combobox").filter({ hasText: "No status selected" }).click({ timeout: 5000 });
  const statuses = page.getByRole("listbox");
  await expect(statuses.getByRole("option", { name: "Closed (Duplicate)" })).toHaveCount(0);
  for (const label of ["New", "In Progress", "Escalated", "Closed (Benign Positive)"]) {
    await expect(statuses.getByRole("option", { name: label, exact: true }).locator("svg[aria-hidden=true]")).toHaveCount(1);
  }
  await statuses.getByRole("option", { name: "Closed (Benign Positive)" }).click({ timeout: 5000 });
  await dialog.getByRole("combobox").filter({ hasText: "No assignee selected" }).click({ timeout: 5000 });
  await page.getByRole("option", { name: "Assign to me" }).click({ timeout: 5000 });
  await dialog.getByRole("button", { name: "Reviewed", exact: true }).click({ timeout: 5000 });
  await expect(dialog.getByRole("button", { name: "Reviewed", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: "Reviewed" })).toHaveCount(0);
  await dialog.getByText("Reviewed", { exact: true }).filter({ visible: true }).click();
  await expect(dialog.getByRole("button", { name: "Remove Reviewed" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Search", exact: true })).toHaveCount(0);
  await dialog.getByRole("textbox", { name: "Analyst note" }).fill("  Reviewed both alerts.  ");
  await apply.click();

  await expect(dialog).toHaveCount(0);
  expect(updates).toEqual([{
    action: "update",
    alert_ids: [1, 2],
    status: "CLOSED_BP",
    assignee: "admin",
    tags: ["Reviewed"],
    note: "Reviewed both alerts.",
  }]);
});

test("read-only alert tags can open universal search", async ({ page }) => {
  await installProductionApiMocks(page);
  const session = apiResponse("/api/v1/auth/session") as { user: typeof adminUser };
  await page.route("**/api/v1/auth/session", (route) => route.fulfill(jsonResponse({
    ...session,
    user: { ...adminUser, role: "AUDITOR" },
  })));
  await page.route(/\/api\/v1\/alerts\/1(?:\?|$)/, (route) => route.fulfill(jsonResponse({
    ...sampleAlert,
    tags: ["phishing"],
  })));

  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto("/alerts/ALT-0000001");
  const detail = page.getByLabel("alert timeline content");
  await expect(detail.getByRole("button", { name: "Remove phishing" })).toHaveCount(0);
  await detail.getByRole("link", { name: "phishing", exact: true }).click({ timeout: 5000 });

  await expect(page.getByRole("textbox", { name: "Search", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove phishing" })).toBeVisible();
});

for (const { resource, singular, sample, buttonLabel, status, forbiddenStatus } of [
  { resource: "cases", singular: "case", sample: sampleCase, buttonLabel: "Closed", status: "CLOSED", forbiddenStatus: "Done" },
  { resource: "tasks", singular: "task", sample: sampleTask, buttonLabel: "Done", status: "DONE", forbiddenStatus: "Closed" },
] as const) {
  test(`${resource} share Bulk Action and replace the previous detail with a selection summary`, async ({ page }) => {
    await installProductionApiMocks(page);
    const prefix = sample.human_id.slice(0, 3);
    const second = { ...sample, id: 2, human_id: `${prefix}-0000002`, title: `Second ${singular}` };
    const previous = { ...sample, id: 3, human_id: `${prefix}-0000003`, title: `Previously opened ${singular}` };
    await page.route(`**/api/v1/${resource}?**`, (route) => route.fulfill(jsonResponse({
      ...emptyPage, items: [sample, second, previous], pages: 1, total: 3,
    })));
    await page.route(`**/api/v1/${resource}/3**`, (route) => route.fulfill(jsonResponse(previous)));
    const updates: unknown[] = [];
    await page.route(`**/api/v1/${resource}/bulk-actions`, async (route) => {
      updates.push(route.request().postDataJSON());
      await route.fulfill(jsonResponse({ updated_count: 2 }));
    });
    await page.setViewportSize({ width: 1920, height: 1000 });
    await page.goto(`/${resource}`);
    await page.getByRole("link", { name: new RegExp(previous.title) }).click();
    const detail = page.getByLabel(`${singular} timeline content`);
    await expect(detail).toBeVisible();

    await page.getByRole("checkbox", { name: `Select ${sample.human_id}` }).press("Space");
    await page.getByRole("checkbox", { name: `Select ${second.human_id}` }).press("Space");
    const summary = page.getByRole("region", { name: "Selection summary" });
    await expect(summary.getByRole("heading")).toHaveText(`2 ${resource} selected`);
    await expect(summary.getByRole("listitem").filter({ hasText: sample.human_id })).toBeVisible();
    await expect(summary.getByRole("listitem").filter({ hasText: second.human_id })).toBeVisible();
    await expect(summary.getByText(previous.human_id)).toHaveCount(0);
    await expect(detail).toHaveCount(0);

    await summary.getByRole("button", { name: `Deselect ${second.human_id}` }).click();
    await expect(summary).toHaveCount(0);
    await expect(detail).toBeVisible();
    await page.getByRole("checkbox", { name: `Select ${second.human_id}` }).press("Space");
    await summary.getByRole("button", { name: "Bulk Action" }).click();
    const dialog = page.getByRole("dialog", { name: "Bulk Action" });
    await dialog.getByRole("combobox").filter({ hasText: "No status selected" }).click();
    await expect(page.getByRole("option", { name: forbiddenStatus, exact: true })).toHaveCount(0);
    await page.getByRole("option", { name: buttonLabel, exact: true }).click();
    if (resource === "cases") await expect(dialog.getByText(/closes open linked alerts as Unresolved/)).toBeVisible();
    await dialog.getByRole("combobox").filter({ hasText: "No assignee selected" }).click();
    await page.getByRole("option", { name: "Assign to me" }).click();
    await dialog.getByRole("button", { name: "Resolved", exact: true }).click();
    await dialog.getByRole("textbox", { name: "Analyst note" }).fill("Reviewed as a group");
    await dialog.getByRole("button", { name: "Apply" }).click();

    await expect(summary).toHaveCount(0);
    await expect(detail).toBeVisible();
    expect(updates).toEqual([{
      entity_ids: [sample.id, second.id], status, assignee: "admin", tags: ["Resolved"], note: "Reviewed as a group",
    }]);
  });
}

test("the shared selection summary keeps checked tasks across pages and works on mobile", async ({ page }) => {
  await installProductionApiMocks(page);
  const second = { ...sampleTask, id: 2, human_id: "TSK-0000002", title: "Task on page two" };
  await page.route("**/api/v1/tasks?**", (route) => {
    const pageNumber = Number(new URL(route.request().url()).searchParams.get("page")) || 1;
    return route.fulfill(jsonResponse({
      ...emptyPage, items: [pageNumber === 2 ? second : sampleTask], page: pageNumber, pages: 2, total: 2,
    }));
  });
  await page.setViewportSize({ width: 700, height: 900 });
  await page.goto("/tasks");
  await page.getByRole("checkbox", { name: `Select ${sampleTask.human_id}` }).press("Space");
  await page.getByRole("button", { name: "2", exact: true }).click();
  await page.getByRole("checkbox", { name: `Select ${second.human_id}` }).press("Space");
  await page.getByRole("button", { name: "Review selection" }).click();
  const summary = page.getByRole("region", { name: "Selection summary" });
  await expect(summary.getByRole("heading")).toHaveText("2 tasks selected");
  await expect(summary.getByText(sampleTask.title)).toBeVisible();
  await expect(summary.getByText(second.title)).toBeVisible();
  await summary.getByRole("button", { name: "Back to list" }).click();
  await expect(page.getByRole("checkbox", { name: `Select ${second.human_id}` })).toBeChecked();
});

test("MCP consent keeps its capability out of request URLs and posts FastMCP fields", async ({ page, baseURL }) => {
  const consentContext = {
    transaction_id: "transaction-123",
    csrf_token: "csrf-456",
    client_name: "Claude Desktop",
    client_id: "client-789",
    client_uri: "https://claude.ai/",
    redirect_uri: "http://127.0.0.1:6274/oauth/callback",
    scopes: ["mcp:access"],
    verified_domain: null,
  };
  let contextRequest:
    | { url: string; body: unknown; cookieHeader: string | null }
    | undefined;
  let consentDecision: Record<string, string> | undefined;

  if (!baseURL) throw new Error("Playwright baseURL is required");
  await page.context().addCookies([
    { name: "intercept_session", value: "existing-session", url: baseURL },
    { name: "XSRF-TOKEN", value: "app-csrf-token", url: baseURL },
  ]);

  await page.route("**/api/v1/auth/session", async (route) => {
    await route.fulfill(jsonResponse({ detail: "Not authenticated" }, 401));
  });
  await page.route("**/api/v1/mcp/oauth/consent/oidc", async (route) => {
    const request = route.request();
    contextRequest = {
      url: request.url(),
      body: request.postDataJSON(),
      cookieHeader: await request.headerValue("cookie"),
    };
    await route.fulfill(jsonResponse(consentContext));
  });
  await page.route(/^https?:\/\/[^/]+\/mcp\/consent$/, async (route) => {
    consentDecision = Object.fromEntries(
      new URLSearchParams(route.request().postData() ?? ""),
    );
    await route.fulfill({
      status: 200,
      contentType: "text/html",
      headers: {
        "Cache-Control": "no-store",
      },
      body: "<!doctype html><title>Consent forwarded</title><p>Consent forwarded</p>",
    });
  });

  const response = await page.goto(
    "/oauth/mcp/consent#txn_id=transaction-123",
    { waitUntil: "domcontentloaded" },
  );

  expect(response?.status()).toBeLessThan(400);
  await expect(
    page.getByRole("heading", { name: "Authorize MCP access" }),
  ).toBeVisible();
  await expect(page.getByText("Claude Desktop wants to connect")).toBeVisible();
  await expect(page.getByText(consentContext.redirect_uri).first()).toBeVisible();

  expect(contextRequest).toEqual({
    url: expect.stringMatching(/\/api\/v1\/mcp\/oauth\/consent\/oidc$/),
    body: { transaction_id: "transaction-123" },
    cookieHeader: null,
  });

  await page.getByRole("button", { name: "Authorize" }).click();
  await expect(page.getByText("Consent forwarded")).toBeVisible();

  expect(consentDecision).toEqual({
    txn_id: "transaction-123",
    csrf_token: "csrf-456",
    submit: "true",
    action: "approve",
  });
});
