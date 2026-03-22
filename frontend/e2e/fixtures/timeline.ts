/**
 * Timeline E2E Test Fixtures and Helpers
 * 
 * Shared utilities for testing timeline functionality across alerts, cases, and tasks.
 */

import { test as base, expect, type Page, type Locator } from '@playwright/test';

/**
 * Entity types supported by the timeline system
 */
export type EntityType = 'alert' | 'case' | 'task';

/**
 * Timeline page object for interacting with timeline components
 */
export class TimelinePage {
  readonly page: Page;
  readonly entityType: EntityType;
  
  constructor(page: Page, entityType: EntityType) {
    this.page = page;
    this.entityType = entityType;
  }
  
  // ============================================================================
  // Locators
  // ============================================================================
  
  /**
   * Quick terminal input field
   */
  get quickTerminalInput(): Locator {
    return this.page.getByRole('combobox', { name: /Type \/ for commands or plain text for quick note/i });
  }
  
  /**
   * Add timeline item button (the + button in quick terminal)
   */
  get addItemButton(): Locator {
    return this.page.getByRole('button', { name: /Add timeline item/i });
  }
  
  /**
   * Timeline items container
   */
  get timelineItems(): Locator {
    return this.page.locator('[id^="timeline-item-"]');
  }
  
  /**
   * Get a specific timeline item by its content
   */
  getTimelineItemByText(text: string): Locator {
    return this.page.locator('[id^="timeline-item-"]').filter({ hasText: text });
  }
  
  /**
   * Get timeline item action buttons (appear on hover)
   * The buttons appear in order: Reply (with text), Flag, Highlight, Delete, Edit
   * Icon-only buttons have a specific size class (h-6 w-6) vs Reply button (w-auto)
   */
  getItemActionButtons(item: Locator): {
    reply: Locator;
    flag: Locator;
    highlight: Locator;
    edit: Locator;
    delete: Locator;
  } {
    // Icon buttons have class 'h-6 w-6' - this distinguishes them from Reply button (w-auto)
    // SVG is nested inside button > span > svg, so we can't use direct child selector
    const iconButtons = item.locator('button.h-6.w-6');
    
    return {
      reply: item.getByRole('button', { name: /Reply/i }),
      // Icon buttons are in order: Flag (index 0), Highlight (1), Delete (2), Edit (3)
      flag: iconButtons.nth(0),
      highlight: iconButtons.nth(1),
      delete: iconButtons.nth(2),
      edit: iconButtons.nth(3),
    };
  }
  
  /**
   * Right dock panel (form editor)
   */
  get rightDock(): Locator {
    return this.page.locator('[data-dock="right"]').or(this.page.locator('.dock-panel'));
  }
  
  /**
   * Form submit button in dock
   * Matches buttons like "Add Note", "Save", "Create Task", "Submit", etc.
   */
  get dockSubmitButton(): Locator {
    return this.page.getByRole('button', { name: /^(Save|Create|Add|Submit)/i }).last();
  }
  
  /**
   * Form cancel button in dock
   */
  get dockCancelButton(): Locator {
    return this.page.getByRole('button', { name: /Cancel/i }).last();
  }
  
  // ============================================================================
  // Navigation
  // ============================================================================
  
  /**
   * Navigate to entity list page
   */
  async navigateToList(): Promise<void> {
    const paths = {
      alert: '/alerts',
      case: '/cases',
      task: '/tasks',
    };
    await this.page.goto(paths[this.entityType]);
    await this.page.waitForLoadState('networkidle');
  }
  
  /**
   * Navigate to a specific entity detail page
   */
  async navigateToDetail(humanId: string): Promise<void> {
    const paths = {
      alert: `/alerts/${humanId}`,
      case: `/cases/${humanId}`,
      task: `/tasks/${humanId}`,
    };
    await this.page.goto(paths[this.entityType]);
    await this.page.waitForLoadState('networkidle');
  }
  
  /**
   * Click first entity in list to navigate to detail
   */
  async clickFirstEntity(): Promise<void> {
    const prefixes = {
      alert: 'ALT-',
      case: 'CAS-',
      task: 'TSK-',
    };
    const firstEntity = this.page.getByRole('link').filter({ hasText: new RegExp(`^${prefixes[this.entityType]}\\d+`) }).first();
    await firstEntity.click();
    await this.page.waitForLoadState('networkidle');
  }
  
  // ============================================================================
  // Quick Terminal Actions
  // ============================================================================
  
  /**
   * Add a quick note via the terminal
   */
  async addQuickNote(text: string): Promise<void> {
    await this.quickTerminalInput.click();
    await this.quickTerminalInput.fill(text);
    await this.page.keyboard.press('Enter');
    // Wait for the note to be created
    await this.waitForTimelineRefresh();
  }
  
  /**
   * Open the add item menu and select an item type
   */
  async openAddItemMenu(): Promise<void> {
    await this.addItemButton.click();
  }
  
  /**
   * Select an item type from the add item menu
   */
  async selectItemType(itemType: string): Promise<void> {
    await this.page.getByRole('menuitem', { name: new RegExp(itemType, 'i') }).click();
  }
  
  /**
   * Use slash command to open form
   */
  async useSlashCommand(command: string): Promise<void> {
    await this.quickTerminalInput.click();
    await this.quickTerminalInput.fill(`/${command}`);
    await this.page.keyboard.press('Enter');
  }
  
  // ============================================================================
  // Timeline Item Actions
  // ============================================================================
  
  /**
   * Wait for timeline to refresh after an action
   */
  async waitForTimelineRefresh(): Promise<void> {
    // Wait a short time for optimistic update, then verify server sync
    await this.page.waitForTimeout(1000);
    await this.page.waitForLoadState('networkidle');
  }
  
  /**
   * Flag a timeline item
   */
  async flagItem(item: Locator): Promise<void> {
    await item.hover();
    const buttons = this.getItemActionButtons(item);
    await buttons.flag.click();
    await this.waitForTimelineRefresh();
  }
  
  /**
   * Highlight a timeline item
   */
  async highlightItem(item: Locator): Promise<void> {
    await item.hover();
    const buttons = this.getItemActionButtons(item);
    await buttons.highlight.click();
    await this.waitForTimelineRefresh();
  }
  
  /**
   * Start editing a timeline item
   */
  async editItem(item: Locator): Promise<void> {
    await item.hover();
    const buttons = this.getItemActionButtons(item);
    await buttons.edit.click();
  }
  
  /**
   * Delete a timeline item
   */
  async deleteItem(item: Locator): Promise<void> {
    await item.hover();
    const buttons = this.getItemActionButtons(item);
    await buttons.delete.click();
    
    // Confirm deletion if dialog appears
    const confirmButton = this.page.getByRole('button', { name: /Confirm|Delete|Yes/i });
    if (await confirmButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await confirmButton.click();
    }
    
    await this.waitForTimelineRefresh();
  }
  
  /**
   * Start replying to a timeline item
   */
  async replyToItem(item: Locator): Promise<void> {
    await item.hover();
    const buttons = this.getItemActionButtons(item);
    await buttons.reply.click();
    // Wait for reply mode to activate
    await this.page.waitForTimeout(300);
  }
  
  /**
   * Submit a reply in the quick terminal (while in reply mode)
   */
  async submitReply(text: string): Promise<void> {
    // When in reply mode, the quick terminal is used for entering reply text
    // The combobox has accessible name with "quick note" or similar
    const replyInput = this.page.getByRole('combobox', { name: /quick note|commands/i });
    await replyInput.fill(text);
    await this.page.keyboard.press('Enter');
    await this.waitForTimelineRefresh();
  }
  
  // ============================================================================
  // Dock Form Actions
  // ============================================================================
  
  /**
   * Fill note form in dock
   */
  async fillNoteForm(description: string): Promise<void> {
    // Try the markdown editor first (editable markdown textbox), then fallback to textarea
    const markdownEditor = this.page.getByRole('textbox', { name: /editable markdown/i });
    const textArea = this.page.locator('textarea');
    const noteInput = this.page.getByRole('textbox', { name: /description|content|note/i }).last();
    
    if (await markdownEditor.isVisible({ timeout: 1000 }).catch(() => false)) {
      await markdownEditor.click();
      await markdownEditor.fill(description);
    } else if (await textArea.isVisible({ timeout: 1000 }).catch(() => false)) {
      await textArea.fill(description);
    } else {
      await noteInput.fill(description);
    }
  }
  
  /**
   * Submit the dock form
   */
  async submitDockForm(): Promise<void> {
    await this.dockSubmitButton.click();
    await this.waitForTimelineRefresh();
  }
  
  /**
   * Cancel the dock form
   */
  async cancelDockForm(): Promise<void> {
    await this.dockCancelButton.click();
  }
  
  // ============================================================================
  // Assertions
  // ============================================================================
  
  /**
   * Assert a timeline item with specific text exists.
   * Uses .first() to avoid strict mode violations when text appears in nested items.
   */
  async assertTimelineItemExists(text: string): Promise<void> {
    const item = this.getTimelineItemByText(text).first();
    await expect(item).toBeVisible();
  }
  
  /**
   * Assert a timeline item with specific text does not exist
   */
  async assertTimelineItemNotExists(text: string): Promise<void> {
    const item = this.getTimelineItemByText(text);
    await expect(item).not.toBeVisible();
  }
  
  /**
   * Assert an item is flagged (has flag icon visible)
   */
  async assertItemFlagged(item: Locator): Promise<void> {
    // Flag icon should be visible in the item header
    const flagIcon = item.locator('img[alt*="flag"], svg[data-icon="flag"], [class*="flag"]').first();
    await expect(flagIcon).toBeVisible();
  }
  
  /**
   * Assert an item is highlighted (has highlight styling)
   */
  async assertItemHighlighted(item: Locator): Promise<void> {
    // Highlighted items have a highlight icon or special styling
    const highlightIcon = item.locator('img[alt*="highlight"], svg[data-icon="highlight"], [class*="highlight"]').first();
    await expect(highlightIcon).toBeVisible();
  }
  
  /**
   * Assert a reply exists under a parent item
   */
  async assertReplyExists(parentItem: Locator, replyText: string): Promise<void> {
    const reply = parentItem.locator('[id^="timeline-item-"]', { hasText: replyText });
    await expect(reply).toBeVisible();
  }
  
  /**
   * Get the count of timeline items
   */
  async getTimelineItemCount(): Promise<number> {
    return await this.timelineItems.count();
  }
}

/**
 * Extended test fixture with TimelinePage
 */
export const test = base.extend<{
  alertTimeline: TimelinePage;
  caseTimeline: TimelinePage;
  taskTimeline: TimelinePage;
}>({
  alertTimeline: async ({ page }, use) => {
    await use(new TimelinePage(page, 'alert'));
  },
  caseTimeline: async ({ page }, use) => {
    await use(new TimelinePage(page, 'case'));
  },
  taskTimeline: async ({ page }, use) => {
    await use(new TimelinePage(page, 'task'));
  },
});

export { expect };

/**
 * Generate a unique test note text
 */
export function generateTestNote(): string {
  return `Test note ${Date.now()}-${Math.random().toString(36).substring(7)}`;
}
