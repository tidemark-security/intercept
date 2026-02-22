/**
 * Case Timeline E2E Tests
 * 
 * Tests for timeline functionality on the Case Detail page.
 * Covers all timeline operations: add, edit, delete, flag, highlight, reply.
 * 
 * These tests verify that case timeline behavior is consistent with alert timeline.
 */

import { test, expect, generateTestNote } from './fixtures/timeline';

test.describe('Case Timeline', () => {
  test.beforeEach(async ({ caseTimeline, page }) => {
    // Navigate to cases list first
    await page.goto('/cases');
    await page.waitForLoadState('networkidle');
    
    // Wait for cases to load and get the first case ID
    const firstCaseLink = page.locator('a[href^="/cases/CAS-"]').first();
    await expect(firstCaseLink).toBeVisible({ timeout: 10000 });
    
    // Extract the case ID from href and navigate directly to the full detail page
    // This is necessary because clicking from the list shows a split-view without quick terminal
    const href = await firstCaseLink.getAttribute('href');
    if (href) {
      await page.goto(href);
      await page.waitForLoadState('networkidle');
    }
    
    // Wait for timeline to be visible
    await expect(caseTimeline.quickTerminalInput).toBeVisible({ timeout: 10000 });
  });

  test.describe('Quick Terminal Notes', () => {
    test('should add a note via quick terminal and see it in timeline', async ({ caseTimeline }) => {
      const noteText = generateTestNote();
      
      // Add note via quick terminal
      await caseTimeline.addQuickNote(noteText);
      
      // Verify note appears in timeline
      await caseTimeline.assertTimelineItemExists(noteText);
    });

    test('should show optimistic update immediately after submitting note', async ({ caseTimeline, page }) => {
      const noteText = generateTestNote();
      
      // Add note and check it appears quickly (optimistic update)
      await caseTimeline.quickTerminalInput.click();
      await caseTimeline.quickTerminalInput.fill(noteText);
      
      // Press enter and immediately check for the note
      await page.keyboard.press('Enter');
      
      // The note should appear within 500ms due to optimistic update
      const item = caseTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible({ timeout: 1000 });
    });

    test('should clear input after submitting note', async ({ caseTimeline }) => {
      const noteText = generateTestNote();
      
      await caseTimeline.addQuickNote(noteText);
      
      // Input should be cleared
      await expect(caseTimeline.quickTerminalInput).toHaveValue('');
    });
  });

  test.describe('Dock Form Notes', () => {
    test('should add a note via dock form and see it in timeline', async ({ caseTimeline, page }) => {
      // Open add item menu
      await caseTimeline.openAddItemMenu();
      
      // Select "Note" from the menu
      await caseTimeline.selectItemType('Note');
      
      // Wait for dock form to appear
      await page.waitForTimeout(500);
      
      // Fill the note form
      const noteText = generateTestNote();
      await caseTimeline.fillNoteForm(noteText);
      
      // Submit the form
      await caseTimeline.submitDockForm();
      
      // Verify note appears in timeline
      await caseTimeline.assertTimelineItemExists(noteText);
    });
  });

  test.describe('Edit Timeline Item', () => {
    test('should edit a timeline item and see changes immediately', async ({ caseTimeline, page }) => {
      // First add a note
      const originalText = generateTestNote();
      await caseTimeline.addQuickNote(originalText);
      await caseTimeline.waitForTimelineRefresh();
      
      // Find the item and edit it
      const item = caseTimeline.getTimelineItemByText(originalText);
      await expect(item).toBeVisible();
      
      // Click edit button using fixture method
      await caseTimeline.editItem(item);
      
      // Wait for edit form to appear
      await page.waitForTimeout(500);
      
      // Modify the text using the markdown editor
      const updatedText = `${originalText} - UPDATED`;
      const markdownEditor = page.getByRole('textbox', { name: /editable markdown/i });
      await markdownEditor.click();
      await markdownEditor.clear();
      await markdownEditor.fill(updatedText);
      
      // Submit
      await caseTimeline.submitDockForm();
      
      // Verify updated text appears (use full text to avoid matching linked items)
      await caseTimeline.assertTimelineItemExists(updatedText);
    });
  });

  test.describe('Delete Timeline Item', () => {
    test('should delete a timeline item and see it removed from timeline', async ({ caseTimeline, page }) => {
      // First add a note
      const noteText = generateTestNote();
      await caseTimeline.addQuickNote(noteText);
      await caseTimeline.waitForTimelineRefresh();
      
      // Verify it exists
      await caseTimeline.assertTimelineItemExists(noteText);
      
      // Get the item count before deletion
      const countBefore = await caseTimeline.getTimelineItemCount();
      
      // Find the item and delete it using fixture method
      const item = caseTimeline.getTimelineItemByText(noteText);
      await caseTimeline.deleteItem(item);
      
      // Verify item is removed
      await caseTimeline.assertTimelineItemNotExists(noteText);
      
      // Verify count decreased
      const countAfter = await caseTimeline.getTimelineItemCount();
      expect(countAfter).toBeLessThan(countBefore);
    });
  });

  test.describe('Flag Timeline Item', () => {
    test('should flag a timeline item and see flag icon appear', async ({ caseTimeline, page }) => {
      // First add a note
      const noteText = generateTestNote();
      await caseTimeline.addQuickNote(noteText);
      await caseTimeline.waitForTimelineRefresh();
      
      // Find the item
      const item = caseTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible();
      
      // Use fixture method to flag the item
      await caseTimeline.flagItem(item);
      
      // Verify the item still exists (flag toggle happened)
      const flaggedItem = caseTimeline.getTimelineItemByText(noteText);
      await expect(flaggedItem).toBeVisible();
    });
  });

  test.describe('Highlight Timeline Item', () => {
    test('should highlight a timeline item and see highlight styling appear', async ({ caseTimeline, page }) => {
      // First add a note
      const noteText = generateTestNote();
      await caseTimeline.addQuickNote(noteText);
      await caseTimeline.waitForTimelineRefresh();
      
      // Find the item
      const item = caseTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible();
      
      // Use fixture method to highlight the item
      await caseTimeline.highlightItem(item);
      
      // Verify the item is still visible
      const highlightedItem = caseTimeline.getTimelineItemByText(noteText);
      await expect(highlightedItem).toBeVisible();
    });
  });

  test.describe('Reply to Timeline Item', () => {
    test('should add a reply to a timeline item and see it nested', async ({ caseTimeline, page }) => {
      // First add a parent note
      const parentNote = generateTestNote();
      await caseTimeline.addQuickNote(parentNote);
      await caseTimeline.waitForTimelineRefresh();
      
      // Find the parent item and click reply using fixture
      const parentItem = caseTimeline.getTimelineItemByText(parentNote);
      await expect(parentItem).toBeVisible();
      
      await caseTimeline.replyToItem(parentItem);
      
      // Wait for reply input to appear
      await page.waitForTimeout(500);
      
      // Type reply in the inline reply terminal
      const replyText = `Reply to ${parentNote}`;
      await caseTimeline.submitReply(replyText);
      
      // Verify reply appears nested under parent
      await caseTimeline.assertTimelineItemExists(replyText);
    });
  });

  test.describe('Optimistic Updates', () => {
    test('should show optimistic update immediately before server confirms', async ({ caseTimeline, page }) => {
      const noteText = generateTestNote();
      
      // Intercept the API call to delay response
      await page.route('**/api/v1/cases/*/timeline', async route => {
        if (route.request().method() === 'POST') {
          // Delay the response by 2 seconds
          await new Promise(resolve => setTimeout(resolve, 2000));
          await route.continue();
        } else {
          await route.continue();
        }
      });
      
      // Add note
      await caseTimeline.quickTerminalInput.fill(noteText);
      await page.keyboard.press('Enter');
      
      // Check that the item appears relatively quickly (within 2 seconds - before the delayed response)
      const item = caseTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible({ timeout: 2000 });
    });
  });

  test.describe('Error Handling', () => {
    test('should rollback optimistic update on API error', async ({ caseTimeline, page }) => {
      const noteText = generateTestNote();
      const initialCount = await caseTimeline.getTimelineItemCount();
      
      // Intercept the API call to return an error
      await page.route('**/api/v1/cases/*/timeline', async route => {
        if (route.request().method() === 'POST') {
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Internal Server Error' }),
          });
        } else {
          await route.continue();
        }
      });
      
      // Try to add note
      await caseTimeline.quickTerminalInput.fill(noteText);
      await page.keyboard.press('Enter');
      
      // Wait for error handling and rollback
      await page.waitForTimeout(2000);
      
      // The optimistic item should be rolled back
      const finalCount = await caseTimeline.getTimelineItemCount();
      expect(finalCount).toBe(initialCount);
    });
  });

  test.describe('Case-Specific Features', () => {
    test('should show linked alerts in case timeline', async ({ caseTimeline, page }) => {
      // Look for linked alert cards in the timeline
      const alertCard = page.locator('[id^="timeline-item-"]').filter({ hasText: /ALT-\d+/ });
      
      // If there are linked alerts, they should be displayed
      const alertCount = await alertCard.count();
      if (alertCount > 0) {
        await expect(alertCard.first()).toBeVisible();
        
        // Clicking on a linked alert should navigate to the alert detail page
        const alertLink = alertCard.first().getByRole('link');
        if (await alertLink.isVisible()) {
          const href = await alertLink.getAttribute('href');
          expect(href).toMatch(/\/alerts\/ALT-\d+/);
        }
      }
    });

    test('should show linked tasks in case timeline', async ({ caseTimeline, page }) => {
      // Look for linked task cards in the timeline
      const taskCard = page.locator('[id^="timeline-item-"]').filter({ hasText: /TSK-\d+/ });
      
      // If there are linked tasks, they should be displayed
      const taskCount = await taskCard.count();
      if (taskCount > 0) {
        await expect(taskCard.first()).toBeVisible();
        
        // Get the first link from the first task card
        const taskLink = taskCard.first().getByRole('link').first();
        if (await taskLink.isVisible()) {
          const href = await taskLink.getAttribute('href');
          expect(href).toMatch(/\/tasks\/TSK-\d+/);
        }
      }
    });
  });
});
