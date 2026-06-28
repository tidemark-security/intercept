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

const runbook = {
  id: 7,
  human_id: "RUN-0000007",
  title: "Credential Theft Response",
  description: "Identity containment and recovery workflow",
  status: "PUBLISHED",
  case_tags: ["identity"],
  runbook_tasks: [
    {
      title: "Review identity provider logs",
      description: "Check suspicious login events",
      picerl_stage: "Identification",
      relative_due_seconds: 3600,
      priority: "HIGH",
      tags: ["identity"],
    },
  ],
  created_at: now,
  updated_at: now,
  created_by: "admin",
  updated_by: "admin",
};

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

async function installApiMocks(page: Page) {
  await page.route("**/api/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/v1/auth/session") {
      await route.fulfill(jsonResponse({
        user: adminUser,
        session: {
          id: "smoke-session",
          user_id: adminUser.id,
          created_at: now,
          expires_at: "2026-01-02T00:00:00.000Z",
        },
        mustChangePassword: false,
      }));
      return;
    }

    if (url.pathname === "/api/v1/auth/oidc/config") {
      await route.fulfill(jsonResponse({ enabled: false, providerName: "SSO" }));
      return;
    }

    if (url.pathname === "/api/v1/features") {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === "/api/v1/case-runbooks" && request.method() === "GET") {
      await route.fulfill(jsonResponse({
        items: [runbook],
        total: 1,
        page: 1,
        size: 50,
        pages: 1,
      }));
      return;
    }

    if (url.pathname === "/api/v1/case-runbooks" && request.method() === "POST") {
      await route.fulfill(jsonResponse({
        ...runbook,
        id: 8,
        human_id: "RUN-0000008",
        title: "Malware Response",
        status: "DRAFT",
      }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });
}

test("case runbooks production route renders and opens the editor", async ({ page }) => {
  await installApiMocks(page);

  const response = await page.goto("/case-runbooks", { waitUntil: "domcontentloaded" });
  expect(response?.status()).toBeLessThan(400);

  await expect(page.getByText("Case Runbooks").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Runbooks" }).first()).toBeVisible();
  await expect(page.getByText("RUN-0000007").first()).toBeVisible();
  await expect(page.getByText("Review identity provider logs")).toBeVisible();
  await expect(page.getByText("Case Templates")).toHaveCount(0);

  await page.getByRole("button", { name: /New Runbook/ }).click();

  await expect(page.getByText("New Case Runbook")).toBeVisible();
  await expect(page.getByLabel("Runbook Title")).toBeVisible();
  await expect(page.getByLabel("Description")).toBeVisible();
  await expect(page.getByText("Runbook Tasks").last()).toBeVisible();

  await page.getByPlaceholder("Credential theft response").fill("Malware Response");
  await page.getByPlaceholder("Review identity provider logs").fill("Isolate host");
  await page.getByRole("button", { name: /Create Runbook/ }).click();
});
