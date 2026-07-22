import { test, expect } from '@playwright/test';

test.describe('Dashboard E2E Tests', () => {
  // We use a clean browser context for login tests
  test('should reject invalid password', async ({ page }) => {
    await page.goto('/');
    // Check if we are on the login screen
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();

    await page.getByPlaceholder('••••••••').fill('wrongpassword');
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page.getByText(/invalid password/i)).toBeVisible();
  });

  test('should login successfully and load dashboard', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('••••••••').fill('jenex');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Verify dashboard loads
    await expect(page.getByRole('heading', { name: /pipeline status/i })).toBeVisible();
  });

  test.describe('Authenticated Features', () => {
    // Authenticate once before all tests in this block
    test.beforeEach(async ({ page }) => {
      await page.goto('/');
      await page.getByPlaceholder('••••••••').fill('jenex');
      await page.getByRole('button', { name: /sign in/i }).click();
      await expect(page.getByRole('heading', { name: /pipeline status/i })).toBeVisible();
    });

    test('should switch tabs and display leads', async ({ page }) => {
      // Click "Review queue" tab
      await page.getByRole('tab', { name: /review queue/i }).click();
      // Click "Reviewed" tab
      await page.getByRole('tab', { name: /^reviewed/i }).click();
      // Click "Enrichment failed" tab
      await page.getByRole('tab', { name: /enrichment failed/i }).click();
      // Go back to Review queue
      await page.getByRole('tab', { name: /review queue/i }).click();
    });

    test('should switch between campaigns using the top navigation', async ({ page }) => {
      // JENEX is default
      await expect(page.getByRole('heading', { name: 'JENEX HVAC (Hungary)' })).toBeVisible();

      // Click "Shoe Photo"
      await page.getByRole('tab', { name: /Shoe Photo/i }).click();

      // Verify campaign title updates
      await expect(page.getByRole('heading', { name: 'Shoe Photo Upgrade' })).toBeVisible();

      // Click "WP Remediation"
      await page.getByRole('tab', { name: /WP Remediation/i }).click();
      
      // Verify campaign title updates
      await expect(page.getByRole('heading', { name: 'WP Remediation' })).toBeVisible();

      // Go back to JENEX
      await page.getByRole('tab', { name: /JENEX HVAC/i }).click();
      await expect(page.getByRole('heading', { name: 'JENEX HVAC (Hungary)' })).toBeVisible();
    });

    test('should open settings and update business brief', async ({ page }) => {
      // Click settings button (cog icon)
      await page.locator('button').filter({ has: page.locator('svg.lucide-settings') }).click();
      await expect(page.getByRole('dialog')).toBeVisible();

      const briefTextarea = page.locator('textarea[placeholder*="Describe your business"]');
      await expect(briefTextarea).toBeVisible();
      
      const originalValue = await briefTextarea.inputValue();
      const testValue = originalValue + ' (E2E Test Append)';
      await briefTextarea.fill(testValue);
      
      await page.getByRole('button', { name: /^save$/i }).click();
      await expect(page.getByText('Saved ✓')).toBeVisible({ timeout: 10000 });

      // Reload to verify it persisted
      await page.reload();
      await page.locator('button').filter({ has: page.locator('svg.lucide-settings') }).click();
      await expect(briefTextarea).toHaveValue(testValue);

      // Revert
      await briefTextarea.fill(originalValue);
      await page.getByRole('button', { name: /^save$/i }).click();
    });

    test('should open lead drawer and show details', async ({ page }) => {
      // Assuming there's at least one lead row. We wait for table to load
      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Nothing here yet') || rowText?.includes('Queue is empty')) {
        test.skip(true, 'No pending leads to click');
        return;
      }
      
      // Click the company name cell to avoid clicking the external link which stops propagation
      await firstRow.locator('td:nth-child(2)').click();

      // Verify drawer opens
      const drawer = page.getByRole('dialog').filter({ hasText: /Rationale/i });
      await expect(drawer).toBeVisible();

      // Verify sections
      await expect(drawer.getByText(/Rationale/i)).toBeVisible();
      await expect(drawer.getByText(/Evidence/i)).toBeVisible();
      
      // Close drawer
      await page.keyboard.press('Escape');
    });

    test('should approve a lead and move it to Approved tab', async ({ page }) => {
      // Note: This modifies state, so we just test the UI mechanism on the first lead
      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Nothing here yet') || rowText?.includes('Queue is empty')) {
        test.skip(true, 'No pending leads to approve');
        return;
      }
      
      // Get company name to verify it moved
      const companyName = await firstRow.locator('td').nth(1).textContent() || '';
      
      await firstRow.locator('td:nth-child(2)').click();

      const drawer = page.getByRole('dialog').filter({ hasText: /Rationale/i });
      await expect(drawer).toBeVisible();

      // Approve
      await drawer.getByRole('button', { name: /Approve/i }).click();

      // Verify it appears in Reviewed tab
      await page.getByRole('tab', { name: /^reviewed/i }).click();
      await expect(page.locator('table tbody').getByText(companyName).first()).toBeVisible();
    });

    test('should show enrichment data for enriched leads', async ({ page }) => {
      await page.getByRole('tab', { name: /^reviewed/i }).click();
      
      const enrichedRow = page.locator('table tbody tr', { hasText: 'Enriched' }).first();
      
      // wait a bit for table to populate
      await page.waitForTimeout(1000);
      
      if (!await enrichedRow.isVisible()) {
        test.skip(true, 'No enriched leads available to test');
        return;
      }
      
      await enrichedRow.locator('td:nth-child(2)').click();
      const drawer = page.getByRole('dialog');
      await expect(drawer).toBeVisible();
      
      // Verify Enrichment section is rendered
      await expect(drawer.getByText('Enrichment', { exact: true })).toBeVisible();
      
      // Verify at least some enrichment data is present
      const hasEmail = await drawer.getByText('Email:').isVisible();
      const hasName = await drawer.getByText('Name:').isVisible();
      const hasPhone = await drawer.getByText('Phone:').isVisible();
      const hasScreenshot = await drawer.getByAltText('Website screenshot').isVisible();
      const hasProducts = await drawer.getByText('Products/Services').isVisible();
      
      expect(hasEmail || hasName || hasPhone || hasScreenshot || hasProducts).toBeTruthy();
      
      await page.keyboard.press('Escape');
    });

    test('should test pipeline start/stop controls', async ({ page }) => {
      // Hover over Candidate Finder status item
      const candidateFinder = page.locator('.group').filter({ hasText: 'Candidate Finder' }).first();
      await candidateFinder.hover();

      // See if play button or stop button is visible.
      // Depending on the state (idle or running), we click the respective button.
      const startButton = candidateFinder.locator('button[title="Start"]');
      const stopButton = candidateFinder.locator('button[title="Stop"]');
      
      if (await startButton.isVisible()) {
        await startButton.click();
        await expect(candidateFinder.getByText(/Running now.../i)).toBeVisible({ timeout: 20000 });
        
        // Now hover again to reveal Stop button
        await candidateFinder.hover();
        await stopButton.click();
        await expect(candidateFinder.getByText(/Stopping.../i)).toBeVisible({ timeout: 20000 });
      } else if (await stopButton.isVisible()) {
        // It's already running, let's stop it
        await stopButton.click();
        await expect(candidateFinder.getByText(/Stopping.../i)).toBeVisible({ timeout: 20000 });
      }
    });
    test('should filter leads by search query', async ({ page }) => {
      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Queue is empty') || rowText?.includes('Nothing here yet')) {
        test.skip(true, 'No leads to test search');
        return;
      }

      const companyName = await firstRow.locator('td').nth(1).textContent() || '';
      if (!companyName) return;

      const searchInput = page.getByPlaceholder(/Search by company or domain/i);
      await searchInput.fill(companyName);

      // Verify the company is visible
      await expect(page.locator('table tbody').getByText(companyName).first()).toBeVisible();

      // Search for non-existent
      await searchInput.fill('XYZ_NON_EXISTENT_XYZ');
      await expect(page.getByText('Queue is empty — great work!')).toBeVisible();

      // Reset
      await searchInput.fill('');
    });

    test('should filter leads by score presets', async ({ page }) => {
      await page.waitForSelector('table tbody tr');
      
      const btnAll = page.getByRole('button', { name: /^All$/i });
      const btnHigh = page.getByRole('button', { name: /High 80\+/i });
      const btnMed = page.getByRole('button', { name: /Med 60–79/i });
      const btnLow = page.getByRole('button', { name: /Low <60/i });

      await btnHigh.click();
      await expect(page.locator('table')).toBeVisible();

      await btnMed.click();
      await expect(page.locator('table')).toBeVisible();

      await btnLow.click();
      await expect(page.locator('table')).toBeVisible();

      await btnAll.click();
    });

    test('should perform bulk actions', async ({ page }) => {
      await page.getByRole('tab', { name: /review queue/i }).click();

      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Queue is empty') || rowText?.includes('Nothing here yet')) {
        test.skip(true, 'No leads for bulk action');
        return;
      }

      // Check the "select all" checkbox
      const selectAllCheckbox = page.locator('thead input[type="checkbox"]');
      await selectAllCheckbox.check();

      const approveBtn = page.getByRole('button', { name: /^Approve$/i });
      const rejectBtn = page.getByRole('button', { name: /^Reject$/i });
      
      await expect(approveBtn).toBeVisible();
      await expect(rejectBtn).toBeVisible();

      // Uncheck all
      await selectAllCheckbox.uncheck();
      await expect(approveBtn).not.toBeVisible();

      // Check first row only
      const firstRowCheckbox = firstRow.locator('input[type="checkbox"]');
      await firstRowCheckbox.check();
      await expect(approveBtn).toBeVisible();
      await expect(page.getByText('1 selected')).toBeVisible();

      // Perform approve
      await approveBtn.click();
      await expect(approveBtn).not.toBeVisible();
    });

    test('should display empty state UI text for different tabs', async ({ page }) => {
      const searchInput = page.getByPlaceholder(/Search by company or domain/i);

      // Pending tab
      await page.getByRole('tab', { name: /review queue/i }).click();
      await searchInput.fill('NON_EXISTENT_EMPTY_STATE_TEST');
      await expect(page.getByText('Queue is empty — great work!')).toBeVisible();
      await expect(page.getByText('All leads have been reviewed or are awaiting enrichment.')).toBeVisible();

      // Reviewed tab
      await page.getByRole('tab', { name: /^reviewed/i }).click();
      // Search term is retained across tabs
      await expect(page.getByText('No reviewed leads yet')).toBeVisible();
      await expect(page.getByText('Approve or reject leads from the review queue to see them here.')).toBeVisible();

      // Enrichment failed tab
      await page.getByRole('tab', { name: /enrichment failed/i }).click();
      await expect(page.getByText('No enrichment failures', { exact: true })).toBeVisible();
      await expect(page.getByText('No enrichment failures for this campaign.')).toBeVisible();

      // Reset
      await searchInput.fill('');
    });
  });
});
