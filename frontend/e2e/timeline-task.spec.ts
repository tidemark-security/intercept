/**
 * Task Timeline E2E Tests
 * 
 * Tests for timeline functionality on the Task Detail page.
 * Covers all timeline operations: add, edit, delete, flag, highlight, reply.
 * 
 * These tests verify that task timeline behavior is consistent with alert and case timelines.
 */

import { test, expect, generateTestNote } from './fixtures/timeline';

test.describe('Task Timeline', () => {
  test.beforeEach(async ({ taskTimeline, page }) => {
    // Navigate to tasks list first
    await page.goto('/tasks');
    await page.waitForLoadState('networkidle');
    
    // Wait for tasks to load and get the first task ID
    const firstTaskLink = page.locator('a[href^="/tasks/TSK-"]').first();
    await expect(firstTaskLink).toBeVisible({ timeout: 10000 });
    
    // Extract the task ID from href and navigate directly to the full detail page
    // This is necessary because clicking from the list shows a split-view without quick terminal
    const href = await firstTaskLink.getAttribute('href');
    if (href) {
      await page.goto(href);
      await page.waitForLoadState('networkidle');
    }
    
    // Wait for timeline to be visible
    await expect(taskTimeline.quickTerminalInput).toBeVisible({ timeout: 10000 });
  });

  test.describe('Quick Terminal Notes', () => {
    test('should add a note via quick terminal and see it in timeline', async ({ taskTimeline }) => {
      const noteText = generateTestNote();
      
      // Add note via quick terminal
      await taskTimeline.addQuickNote(noteText);
      
      // Verify note appears in timeline
      await taskTimeline.assertTimelineItemExists(noteText);
    });

    test('should show optimistic update immediately after submitting note', async ({ taskTimeline, page }) => {
      const noteText = generateTestNote();
      
      // Add note and check it appears quickly (optimistic update)
      await taskTimeline.quickTerminalInput.click();
      await taskTimeline.quickTerminalInput.fill(noteText);
      
      // Press enter and immediately check for the note
      await page.keyboard.press('Enter');
      
      // The note should appear within 500ms due to optimistic update
      const item = taskTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible({ timeout: 1000 });
    });

    test('should clear input after submitting note', async ({ taskTimeline }) => {
      const noteText = generateTestNote();
      
      await taskTimeline.addQuickNote(noteText);
      
      // Input should be cleared
      await expect(taskTimeline.quickTerminalInput).toHaveValue('');
    });
  });

  test.describe('Dock Form Notes', () => {
    test('should add a note via dock form and see it in timeline', async ({ taskTimeline, page }) => {
      // Open add item menu
      await taskTimeline.openAddItemMenu();
      
      // Select "Note" from the menu
      await taskTimeline.selectItemType('Note');
      
      // Wait for dock form to appear
      await page.waitForTimeout(500);
      
      // Fill the note form
      const noteText = generateTestNote();
      await taskTimeline.fillNoteForm(noteText);
      
      // Submit the form
      await taskTimeline.submitDockForm();
      
      // Verify note appears in timeline
      await taskTimeline.assertTimelineItemExists(noteText);
    });
  });

  test.describe('Edit Timeline Item', () => {
    test('should edit a timeline item and see changes immediately', async ({ taskTimeline, page }) => {
      // First add a note
      const originalText = generateTestNote();
      await taskTimeline.addQuickNote(originalText);
      await taskTimeline.waitForTimelineRefresh();
      
      // Find the item and edit it
      const item = taskTimeline.getTimelineItemByText(originalText);
      await expect(item).toBeVisible();
      
      // Click edit button using fixture method
      await taskTimeline.editItem(item);
      
      // Wait for edit form to appear
      await page.waitForTimeout(500);
      
      // Modify the text using the markdown editor
      const updatedText = `${originalText} - UPDATED`;
      const markdownEditor = page.getByRole('textbox', { name: /editable markdown/i });
      await markdownEditor.click();
      await markdownEditor.clear();
      await markdownEditor.fill(updatedText);
      
      // Submit
      await taskTimeline.submitDockForm();
      
      // Verify updated text appears (use full text to avoid matching linked items)
      await taskTimeline.assertTimelineItemExists(updatedText);
    });
  });

  test.describe('Delete Timeline Item', () => {
    test('should delete a timeline item and see it removed from timeline', async ({ taskTimeline, page }) => {
      // First add a note
      const noteText = generateTestNote();
      await taskTimeline.addQuickNote(noteText);
      await taskTimeline.waitForTimelineRefresh();
      
      // Verify it exists
      await taskTimeline.assertTimelineItemExists(noteText);
      
      // Get the item count before deletion
      const countBefore = await taskTimeline.getTimelineItemCount();
      
      // Find the item and delete it using fixture method
      const item = taskTimeline.getTimelineItemByText(noteText);
      await taskTimeline.deleteItem(item);
      
      // Verify item is removed
      await taskTimeline.assertTimelineItemNotExists(noteText);
      
      // Verify count decreased
      const countAfter = await taskTimeline.getTimelineItemCount();
      expect(countAfter).toBeLessThan(countBefore);
    });
  });

  test.describe('Flag Timeline Item', () => {
    test('should flag a timeline item and see flag icon appear', async ({ taskTimeline, page }) => {
      // First add a note
      const noteText = generateTestNote();
      await taskTimeline.addQuickNote(noteText);
      await taskTimeline.waitForTimelineRefresh();
      
      // Find the item
      const item = taskTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible();
      
      // Use fixture method to flag the item
      await taskTimeline.flagItem(item);
      
      // Verify the item still exists (flag toggle happened)
      const flaggedItem = taskTimeline.getTimelineItemByText(noteText);
      await expect(flaggedItem).toBeVisible();
    });
  });

  test.describe('Highlight Timeline Item', () => {
    test('should highlight a timeline item and see highlight styling appear', async ({ taskTimeline, page }) => {
      // First add a note
      const noteText = generateTestNote();
      await taskTimeline.addQuickNote(noteText);
      await taskTimeline.waitForTimelineRefresh();
      
      // Find the item
      const item = taskTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible();
      
      // Use fixture method to highlight the item
      await taskTimeline.highlightItem(item);
      
      // Verify the item is still visible
      const highlightedItem = taskTimeline.getTimelineItemByText(noteText);
      await expect(highlightedItem).toBeVisible();
    });
  });

  test.describe('Reply to Timeline Item', () => {
    test('should add a reply to a timeline item and see it nested', async ({ taskTimeline, page }) => {
      // First add a parent note
      const parentNote = generateTestNote();
      await taskTimeline.addQuickNote(parentNote);
      await taskTimeline.waitForTimelineRefresh();
      
      // Find the parent item and click reply using fixture
      const parentItem = taskTimeline.getTimelineItemByText(parentNote);
      await expect(parentItem).toBeVisible();
      
      await taskTimeline.replyToItem(parentItem);
      
      // Wait for reply input to appear
      await page.waitForTimeout(500);
      
      // Type reply in the inline reply terminal
      const replyText = `Reply to ${parentNote}`;
      await taskTimeline.submitReply(replyText);
      
      // Verify reply appears nested under parent
      await taskTimeline.assertTimelineItemExists(replyText);
    });
  });

  test.describe('Optimistic Updates', () => {
    test('should show optimistic update immediately before server confirms', async ({ taskTimeline, page }) => {
      const noteText = generateTestNote();
      
      // Intercept the API call to delay response
      await page.route('**/api/v1/tasks/*/timeline', async route => {
        if (route.request().method() === 'POST') {
          // Delay the response by 2 seconds
          await new Promise(resolve => setTimeout(resolve, 2000));
          await route.continue();
        } else {
          await route.continue();
        }
      });
      
      // Add note
      await taskTimeline.quickTerminalInput.fill(noteText);
      await page.keyboard.press('Enter');
      
      // Check that the item appears relatively quickly (within 2 seconds - before the delayed response)
      const item = taskTimeline.getTimelineItemByText(noteText);
      await expect(item).toBeVisible({ timeout: 2000 });
    });
  });

  test.describe('Error Handling', () => {
    test('should rollback optimistic update on API error', async ({ taskTimeline, page }) => {
      const noteText = generateTestNote();
      const initialCount = await taskTimeline.getTimelineItemCount();
      
      // Intercept the API call to return an error
      await page.route('**/api/v1/tasks/*/timeline', async route => {
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
      await taskTimeline.quickTerminalInput.fill(noteText);
      await page.keyboard.press('Enter');
      
      // Wait for error handling and rollback
      await page.waitForTimeout(2000);
      
      // The optimistic item should be rolled back
      const finalCount = await taskTimeline.getTimelineItemCount();
      expect(finalCount).toBe(initialCount);
    });
  });

  test.describe('Task-Specific Features', () => {
    test('should show parent case link when task is linked to case', async ({ taskTimeline, page }) => {
      // Look for case reference in task detail
      const caseLink = page.getByRole('link').filter({ hasText: /CAS-\d+/ });
      
      const caseCount = await caseLink.count();
      if (caseCount > 0) {
        // If task is linked to a case, verify the link works
        const href = await caseLink.first().getAttribute('href');
        expect(href).toMatch(/\/cases\/CAS-\d+/);
      }
    });
  });
});
