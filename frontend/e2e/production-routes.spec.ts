import { expect, test, type Locator, type Page, type Route } from "@playwright/test";

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
      expect(rootText, `${routePath} should not be stuck on auth loading`).not.toBe("Loading...");

      const routeFailures = failures.splice(0);
      expect(routeFailures, `${routePath} production runtime errors`).toEqual([]);
    });
  }
});

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
    const trigger = page.getByRole("button", { name: /^Assignee/ });
    const entityLinks = page.locator(`a[href^="/${resource}/${prefix}-"]`);
    const choose = async (name: string) => {
      const option = page.getByRole("menuitem", { name, exact: true });
      if (!await option.isVisible()) await trigger.click();
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
  });
}

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

test("alert detail shows Analyst Context before AI Triage without repeating context", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.addInitScript(() => localStorage.setItem("intercept.theme-preference", "system"));
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
    await expect(timeline.getByText(contextBody, { exact: true })).toHaveCount(1);
    await expect(context.getByText("Matched Context", { exact: true })).toHaveCount(0);
    await expect(context.getByRole("button", { name: /Expires in 7 days/ })).toBeVisible();
    const triageCard = timeline.getByRole("region", { name: "AI Triage Recommendation" });
    await expect(triageCard.getByText("Context included", { exact: true })).toBeVisible();
    await expect(triageCard.getByRole("progressbar")).toHaveCount(0);
    const triageHeader = triageCard.locator("header");
    const confidence = triageHeader.getByText("80%", { exact: true });
    const disposition = triageHeader.getByText("Needs Investigation", { exact: true });
    const action = triageCard.getByText("Escalate to case and investigate", { exact: true }).locator("..");
    await expect(confidence).toBeVisible();
    await expect(disposition).toBeVisible();
    await expect(triageHeader.getByText("Pending Review", { exact: true })).toHaveCount(0);
    await expect(action).toBeVisible();
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
      const contextToChevron = await triageHeader.getByText("Context included", { exact: true }).evaluate((element) => {
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
    await expect(accept).toHaveCSS("height", "32px");
    if (width === 390) {
      expect(await top(firstTask)).toBeGreaterThan(await top(taskLabel));
      await triageHeader.getByRole("button", { name: "Collapse triage recommendation" }).click();
      await expect(action).toBeVisible();
      await expect(triageCard.getByText("The evidence is incomplete.", { exact: true }).filter({ visible: true })).toHaveCount(1);
      await expect(accept).toHaveCSS("height", "24px");
      await expect(action).toHaveCSS("height", "24px");
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
  await page.route(/\/api\/v1\/alerts\/[12](?:\?|$)/, (route) => {
    const alert = new URL(route.request().url()).pathname.endsWith("/1") ? sampleAlert : secondAlert;
    const entry = { id: 17, body: `# Test context\n\nContext for ${alert.human_id}.`, author: "admin", criteria: [] };
    return route.fulfill(jsonResponse({
      ...alert,
      context: { items: [entry], total_count: 1 },
      triage_recommendation: {
        id: alert.id,
        alert_id: alert.id,
        created_at: now,
        created_by: "tidemark_ai",
        status: "PENDING",
        disposition: "NEEDS_INVESTIGATION",
        confidence: 0.8,
        request_escalate_to_case: true,
        suggested_status: "ESCALATED",
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
  const action = triage.getByText("Escalate to case and investigate", { exact: true }).locator("..");
  const openAlert = async (alert: typeof sampleAlert) => {
    await page.getByRole("link", { name: new RegExp(alert.title) }).click();
    await expect(page).toHaveURL(new RegExp(`/alerts/${alert.human_id}$`));
    await expect(context.getByText(new RegExp(`Context for ${alert.human_id}`))).toBeVisible();
  };

  await expect(collapseTriage).toHaveAttribute("aria-expanded", "true");
  await collapseContext.click();
  await openAlert(secondAlert);
  await expect(expandContext).toHaveAttribute("aria-expanded", "false");
  await expect(accept).toBeVisible();
  await collapseTriage.press("Space");
  await expect(expandTriage).toBeFocused();
  await openAlert(sampleAlert);
  await page.reload();
  await expect(expandContext).toHaveAttribute("aria-expanded", "false");
  await expect(expandTriage).toHaveAttribute("aria-expanded", "false");
  await expect(action).toBeVisible();
  const reasonPreview = triage.getByText("More evidence is needed. See the triage guide.", { exact: true }).filter({ visible: true });
  await expect(reasonPreview).toBeVisible();
  await expect(reasonPreview.locator("strong, a")).toHaveCount(0);
  const previewBounds = (await reasonPreview.boundingBox())!;
  await expect(accept).toHaveCSS("height", "24px");
  await expect(reject).toHaveCSS("height", "24px");
  await expect(action).toHaveCSS("height", "24px");
  const buttonLabelSize = await accept.getByText("Accept Recommendation", { exact: true })
    .evaluate((label) => getComputedStyle(label).fontSize);
  await expect(action).toHaveCSS("font-size", buttonLabelSize);
  await expect(triage.getByRole("button", { name: /^Reasoning/ })).toHaveCount(0);
  const bannerBounds = (await action.boundingBox())!;
  const acceptBounds = (await accept.boundingBox())!;
  const headerBounds = (await triage.locator("header").boundingBox())!;
  expect(previewBounds.y).toBeGreaterThanOrEqual(headerBounds.y + headerBounds.height);
  expect(bannerBounds.y).toBeGreaterThanOrEqual(previewBounds.y + previewBounds.height);
  expect(acceptBounds.x).toBeGreaterThan(bannerBounds.x + bannerBounds.width);
  expect(acceptBounds.y + acceptBounds.height / 2).toBeCloseTo(bannerBounds.y + bannerBounds.height / 2, 0);

  await expandTriage.click();
  await openAlert(secondAlert);
  await expect(expandContext).toHaveAttribute("aria-expanded", "false");
  await expect(accept).toHaveCSS("height", "32px");
  await expandContext.click();
  await page.reload();
  await expect(collapseContext).toHaveAttribute("aria-expanded", "true");
  await expect(collapseTriage).toHaveAttribute("aria-expanded", "true");
});

test("narrow alerts view keeps the queue and detail reachable", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.goto("/alerts");
  const alertLinks = page.locator('a[href^="/alerts/ALT-"]');
  await alertLinks.first().click();

  const list = page.getByRole("region", { name: "Alert list", exact: true });
  const detail = page.getByRole("region", { name: "Alert detail", exact: true });
  const paneScale = (pane: Locator) => pane.evaluate((el) => el.getBoundingClientRect().width / el.clientWidth);
  await expect(detail).toBeFocused();
  await expect.poll(() => paneScale(list)).toBeCloseTo(0.98, 2);

  // Each pane retains a reachable edge when behind the other pane.
  await list.hover({ position: { x: 30, y: 100 } });
  await expect.poll(() => paneScale(list)).toBeCloseTo(1, 2);
  await expect.poll(() => paneScale(detail)).toBeCloseTo(0.98, 2);
  const detailBounds = await detail.boundingBox();
  if (!detailBounds) throw new Error("Expected the detail edge to remain visible");
  await detail.hover({ position: { x: detailBounds.width - 30, y: 100 } });
  await expect.poll(() => paneScale(detail)).toBeCloseTo(1, 2);

  const nextAlert = list.getByRole("link", { name: /Second smoke alert/ });
  await nextAlert.focus();
  await expect.poll(() => paneScale(list)).toBeCloseTo(1, 2);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/alerts\/ALT-0000002$/);
  await expect(detail).toBeFocused();
  await expect.poll(() => paneScale(detail)).toBeCloseTo(1, 2);

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(list).toBeVisible();
  await expect(detail).toBeVisible();

  await page.setViewportSize({ width: 700, height: 900 });
  await expect(list).toHaveCount(0);
  await expect(alertLinks).toHaveCount(0);
  await expect(page.getByLabel("alert timeline content")).toBeVisible();

  await page.setViewportSize({ width: 1920, height: 900 });
  await expect(alertLinks.first()).toBeVisible();
  await expect(page.getByLabel("alert timeline content")).toBeVisible();
  await expect(list).toHaveCount(0);
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

test("the narrow alerts overlay can bring the selection summary and list to the front", async ({ page }) => {
  await installProductionApiMocks(page);
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.goto("/alerts/ALT-0000001");
  const list = page.getByRole("region", { name: "Alert list", exact: true });
  await list.getByRole("checkbox", { name: "Select visible alerts" }).press("Space");
  const summary = page.getByRole("region", { name: "Selection summary" });
  await page.getByRole("button", { name: "Review selection" }).click();
  await expect(page.getByRole("region", { name: "Alert detail", exact: true })).toBeFocused();
  await expect(summary.getByRole("heading")).toHaveText("2 alerts selected");
  await summary.getByRole("button", { name: "Back to list" }).click();
  await expect(list).toBeFocused();
  await expect(list.getByRole("checkbox", { name: "Select visible alerts" })).toBeChecked();
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
