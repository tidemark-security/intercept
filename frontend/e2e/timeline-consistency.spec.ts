/**
 * Cross-Entity Timeline Consistency Tests
 * 
 * These tests verify that timeline functionality works identically across
 * alerts, cases, and tasks. This is the primary goal from TIMELINE-IMPROVEMENTS.md.
 */

import { test, expect, generateTestNote, TimelinePage } from './fixtures/timeline';
import type { Page } from '@playwright/test';

/**
 * Test a specific timeline operation across all entity types
 */
async function testAcrossEntities(
  page: Page,
  testFn: (timeline: TimelinePage, page: Page, entityType: string) => Promise<void>
) {
  const entityTypes = ['alert', 'case', 'task'] as const;
  const paths = {
    alert: '/alerts',
    case: '/cases',
    task: '/tasks',
  };
  const hrefPrefixes = {
    alert: '/alerts/ALT-',
    case: '/cases/CAS-',
    task: '/tasks/TSK-',
  };

  for (const entityType of entityTypes) {
    // Navigate to list page
    await page.goto(paths[entityType]);
    await page.waitForLoadState('networkidle');
    
    // Get first entity link href and navigate directly to detail page
    // This is necessary because clicking from list shows split-view without quick terminal
    const firstEntity = page.locator(`a[href^="${hrefPrefixes[entityType]}"]`).first();
    await expect(firstEntity).toBeVisible({ timeout: 10000 });
    
    const href = await firstEntity.getAttribute('href');
    if (href) {
      await page.goto(href);
      await page.waitForLoadState('networkidle');
    }
    
    // Create timeline helper and run test
    const timeline = new TimelinePage(page, entityType);
    await expect(timeline.quickTerminalInput).toBeVisible({ timeout: 10000 });
    
    await testFn(timeline, page, entityType);
  }
}

test.describe('Cross-Entity Timeline Consistency', () => {
  test('Quick terminal note submission works identically across all entity types', async ({ page }) => {
    await testAcrossEntities(page, async (timeline, page, entityType) => {
      const noteText = `${entityType.toUpperCase()} - ${generateTestNote()}`;
      
      // Add note via quick terminal
      await timeline.addQuickNote(noteText);
      
      // Verify note appears
      await timeline.assertTimelineItemExists(noteText);
      
      // Verify input is cleared
      await expect(timeline.quickTerminalInput).toHaveValue('');
    });
  });

  test('Timeline item edit works identically across all entity types', async ({ page }) => {
    await testAcrossEntities(page, async (timeline, page, entityType) => {
      // Add a note
      const originalText = `${entityType.toUpperCase()} - ${generateTestNote()}`;
      await timeline.addQuickNote(originalText);
      await timeline.waitForTimelineRefresh();
      
      // Find and edit the item using fixture method
      const item = timeline.getTimelineItemByText(originalText);
      await expect(item).toBeVisible();
      
      await timeline.editItem(item);
      await page.waitForTimeout(500);
      
      // Update text using markdown editor
      const updatedText = `EDITED-${entityType.toUpperCase()}`;
      const markdownEditor = page.getByRole('textbox', { name: /editable markdown/i });
      await markdownEditor.click();
      await markdownEditor.clear();
      await markdownEditor.fill(updatedText);
      
      // Submit
      await timeline.submitDockForm();
      
      // Verify updated text appears
      await timeline.assertTimelineItemExists(updatedText);
    });
  });

  test('Timeline item delete works identically across all entity types', async ({ page }) => {
    await testAcrossEntities(page, async (timeline, page, entityType) => {
      // Add a note
      const noteText = `${entityType.toUpperCase()} - ${generateTestNote()}`;
      await timeline.addQuickNote(noteText);
      await timeline.waitForTimelineRefresh();
      
      // Get count before
      const countBefore = await timeline.getTimelineItemCount();
      
      // Find and delete the item using fixture method
      const item = timeline.getTimelineItemByText(noteText);
      await timeline.deleteItem(item);
      
      // Verify deleted
      await timeline.assertTimelineItemNotExists(noteText);
      const countAfter = await timeline.getTimelineItemCount();
      expect(countAfter).toBeLessThan(countBefore);
    });
  });

  test('Timeline item flag toggle works identically across all entity types', async ({ page }) => {
    await testAcrossEntities(page, async (timeline, page, entityType) => {
      // Add a note
      const noteText = `${entityType.toUpperCase()} - ${generateTestNote()}`;
      await timeline.addQuickNote(noteText);
      await timeline.waitForTimelineRefresh();
      
      // Find and flag the item using fixture method
      const item = timeline.getTimelineItemByText(noteText);
      await timeline.flagItem(item);
      
      // Item should still exist
      await timeline.assertTimelineItemExists(noteText);
      
      // Unflag using fixture method
      const itemAfterFlag = timeline.getTimelineItemByText(noteText);
      await timeline.flagItem(itemAfterFlag);
      
      // Item should still exist
      await timeline.assertTimelineItemExists(noteText);
    });
  });

  test('Timeline item highlight toggle works identically across all entity types', async ({ page }) => {
    await testAcrossEntities(page, async (timeline, page, entityType) => {
      // Add a note
      const noteText = `${entityType.toUpperCase()} - ${generateTestNote()}`;
      await timeline.addQuickNote(noteText);
      await timeline.waitForTimelineRefresh();
      
      // Find and highlight the item using fixture method
      const item = timeline.getTimelineItemByText(noteText);
      await timeline.highlightItem(item);
      
      // Item should still exist
      await timeline.assertTimelineItemExists(noteText);
    });
  });

  test('Reply to timeline item works identically across all entity types', async ({ page }) => {
    await testAcrossEntities(page, async (timeline, page, entityType) => {
      // Add a parent note
      const parentNote = `${entityType.toUpperCase()} - ${generateTestNote()}`;
      await timeline.addQuickNote(parentNote);
      await timeline.waitForTimelineRefresh();
      
      // Find and reply to the item using fixture method
      const parentItem = timeline.getTimelineItemByText(parentNote);
      await timeline.replyToItem(parentItem);
      await page.waitForTimeout(500);
      
      // Type reply using fixture method
      const replyText = `Reply to ${parentNote}`;
      await timeline.submitReply(replyText);
      
      // Verify reply appears
      await timeline.assertTimelineItemExists(replyText);
    });
  });

  test('Optimistic updates work identically across all entity types', async ({ page }) => {
    const entityTypes = ['alert', 'case', 'task'] as const;
    const paths = {
      alert: '/alerts',
      case: '/cases',
      task: '/tasks',
    };
    const hrefPrefixes = {
      alert: '/alerts/ALT-',
      case: '/cases/CAS-',
      task: '/tasks/TSK-',
    };

    for (const entityType of entityTypes) {
      // Navigate to list page
      await page.goto(paths[entityType]);
      await page.waitForLoadState('networkidle');
      
      // Get first entity link and navigate directly to detail page
      const firstEntity = page.locator(`a[href^="${hrefPrefixes[entityType]}"]`).first();
      await expect(firstEntity).toBeVisible({ timeout: 10000 });
      
      const href = await firstEntity.getAttribute('href');
      if (href) {
        await page.goto(href);
        await page.waitForLoadState('networkidle');
      }
      
      // Create timeline helper
      const timeline = new TimelinePage(page, entityType);
      await expect(timeline.quickTerminalInput).toBeVisible({ timeout: 10000 });
      
      const noteText = `OPTIMISTIC-${entityType.toUpperCase()}-${generateTestNote()}`;
      
      // Add note
      await timeline.quickTerminalInput.fill(noteText);
      await page.keyboard.press('Enter');
      
      // Check item appears immediately (within 1s - optimistic update)
      const item = timeline.getTimelineItemByText(noteText).first();
      await expect(item).toBeVisible({ timeout: 1000 });
      
      // Wait for server to confirm
      await timeline.waitForTimelineRefresh();
    }
  });
});

test.describe('Timeline Feature Parity Check', () => {
  /**
   * This test documents which features should work the same across all entity types.
   * Use this as a reference when adding new timeline features.
   */
  test('Document expected timeline features across entity types', async ({ page }) => {
    const expectedFeatures = [
      'Add note via quick terminal',
      'Add note via dock form',
      'Add note via slash command',
      'Edit timeline item',
      'Delete timeline item',
      'Flag timeline item',
      'Unflag timeline item',
      'Highlight timeline item',
      'Unhighlight timeline item',
      'Reply to timeline item',
      'Optimistic updates on create',
      'Optimistic updates on edit',
      'Optimistic updates on delete',
      'Error rollback on API failure',
      'Clear input after submission',
      'Escape to exit reply mode',
    ];

    // This test serves as documentation - actual tests are in individual spec files
    expect(expectedFeatures.length).toBeGreaterThan(0);
  });
});
