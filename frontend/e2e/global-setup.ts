/**
 * Playwright Global Setup
 * 
 * Handles authentication before tests run.
 * Creates a storage state file that can be reused across tests.
 */

import { chromium, type FullConfig } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

// ES Module compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Storage state file for authenticated session
export const STORAGE_STATE_PATH = path.join(__dirname, '.auth/user.json');

async function globalSetup(config: FullConfig) {
  const { baseURL } = config.projects[0].use;
  
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    // Navigate to login page
    await page.goto(`${baseURL}/login`);
    await page.waitForLoadState('networkidle');
    
    // Check if already authenticated (redirected to home)
    if (!page.url().includes('/login')) {
      console.log('Already authenticated, skipping login');
      await context.storageState({ path: STORAGE_STATE_PATH });
      await browser.close();
      return;
    }
    
    // Fill in login credentials
    // Use environment variables or default test credentials
    const username = process.env.TEST_USERNAME || 'admin';
    const password = process.env.TEST_PASSWORD || 'admin';
    
    // Find and fill the username field
    const usernameField = page.locator('input[type="text"], input[name="username"], input[placeholder*="username" i], input[placeholder*="email" i]').first();
    await usernameField.fill(username);
    
    // Find and fill the password field
    const passwordField = page.locator('input[type="password"]').first();
    await passwordField.fill(password);
    
    // Click the "Sign in with Password" button specifically
    const signInButton = page.getByRole('button', { name: 'Sign in with Password' });
    await signInButton.click();
    
    // Wait for navigation to complete (should redirect to home or dashboard)
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    
    console.log('Successfully logged in, saving storage state');
    
    // Save the authenticated state
    await context.storageState({ path: STORAGE_STATE_PATH });
  } catch (error) {
    console.error('Failed to authenticate:', error);
    throw error;
  } finally {
    await browser.close();
  }
}

export default globalSetup;
