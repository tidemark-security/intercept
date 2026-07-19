import { expect, test } from '@playwright/test';

test.describe('Case Runbooks', () => {
  test('creates, publishes, and applies a case runbook from a case timeline', async ({ page }) => {
    const suffix = Date.now();
    const runbookTitle = `PW Case Runbook ${suffix}`;
    const taskTitle = `PW Runbook Task ${suffix}`;

    await page.goto('/case-runbooks');
    await page.waitForLoadState('networkidle');

    await expect(page.getByRole('heading', { name: 'Case Runbooks' })).toBeVisible();
    await page.getByRole('button', { name: 'New Runbook' }).click();

    await page.getByPlaceholder('Credential theft response').fill(runbookTitle);
    await page.getByPlaceholder('When to use this runbook and what it covers').fill('Playwright response runbook');
    await page.getByPlaceholder('Review identity provider logs').fill(taskTitle);
    const createResponsePromise = page.waitForResponse((response) =>
      response.url().includes('/api/v1/case-runbooks') && response.request().method() === 'POST'
    );
    await page.getByRole('button', { name: 'Create Runbook' }).click();
    const createResponse = await createResponsePromise;
    expect(createResponse.ok(), await createResponse.text()).toBeTruthy();

    await expect(page.getByText(runbookTitle).first()).toBeVisible({ timeout: 10_000 });
    const publishResponsePromise = page.waitForResponse((response) =>
      response.url().includes('/api/v1/case-runbooks') &&
      response.url().includes('/publish') &&
      response.request().method() === 'POST'
    );
    await page.getByRole('button', { name: 'Publish', exact: true }).click();
    const publishResponse = await publishResponsePromise;
    expect(publishResponse.ok(), await publishResponse.text()).toBeTruthy();
    await expect(page.getByText('PUBLISHED').first()).toBeVisible({ timeout: 10_000 });

    await page.goto('/cases');
    await page.waitForLoadState('networkidle');

    const firstCaseLink = page.locator('a[href^="/cases/CAS-"]').first();
    await expect(firstCaseLink).toBeVisible({ timeout: 10_000 });
    const href = await firstCaseLink.getAttribute('href');
    expect(href).toBeTruthy();

    await page.goto(href!);
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: /Add timeline item/i })).toBeVisible();

    await page.getByRole('button', { name: /Add timeline item/i }).click();
    await page.getByRole('menuitem', { name: /Case Runbook/i }).click();

    await expect(page.getByText('Apply published response work to this case')).toBeVisible();
    await page.getByPlaceholder('Search published runbooks').fill(runbookTitle);
    await expect(page.getByText(runbookTitle).first()).toBeVisible({ timeout: 10_000 });
    await page.getByText(runbookTitle).first().click();
    await expect(page.getByText(taskTitle)).toBeVisible();

    const applyResponsePromise = page.waitForResponse((response) =>
      response.url().includes('/api/v1/case-runbooks/cases/') && response.request().method() === 'POST'
    );
    await page.getByTestId('case-runbook-apply-button').click();
    const applyResponse = await applyResponsePromise;
    expect(applyResponse.ok(), await applyResponse.text()).toBeTruthy();
    await expect(page.locator('.text-error-1000')).toHaveCount(0);
    await expect(page.getByText('Preparation').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(taskTitle).first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole('button', { name: /Swimlane/i }).click();
    await expect(page.getByRole('button', { name: 'Identification', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Lessons Learned', exact: true })).toBeVisible();
    await expect(page.getByText(taskTitle).first()).toBeVisible();

    await page.getByRole('button', { name: 'Timeline', exact: true }).click();
    await page.getByRole('button', { name: /Preparation\s+\d+\/\d+/i }).click();
    await expect(page.getByText(taskTitle).first()).toBeVisible();
  });
});
