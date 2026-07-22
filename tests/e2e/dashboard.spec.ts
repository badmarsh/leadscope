import { test, expect, Page } from '@playwright/test';

async function login(page: Page) {
  await page.goto('/');
  // Wait for initial "Loading..." state to finish
  await page.waitForFunction(() => !document.body.innerText.includes('Loading…'), { timeout: 5000 }).catch(() => {});

  const pwdInput = page.getByPlaceholder('••••••••');
  if (await pwdInput.isVisible({ timeout: 3000 })) {
    await pwdInput.fill('jenex');
    await Promise.all([
      page.waitForResponse((res) => res.url().includes('/api/login') && res.status() === 200),
      page.getByRole('button', { name: /sign in/i }).click(),
    ]);
  }
}

test.describe('Dashboard E2E Tests', () => {

  test('should reject invalid password', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => !document.body.innerText.includes('Loading…'), { timeout: 5000 }).catch(() => {});

    const pwdInput = page.getByPlaceholder('••••••••');
    if (await pwdInput.isVisible({ timeout: 3000 })) {
      await pwdInput.fill('wrongpassword');
      await page.getByRole('button', { name: /sign in/i }).click();
      await expect(page.getByText(/invalid password/i)).toBeVisible();
    }
  });

  test('should login successfully and load dashboard', async ({ page }) => {
    await login(page);
    await expect(page.getByRole('heading', { name: 'JENEX HVAC (Hungary)' })).toBeVisible({ timeout: 15000 });
  });

  test.describe('Authenticated Features', () => {
    test.beforeEach(async ({ page }) => {
      await login(page);
      await expect(page.getByRole('heading', { name: 'JENEX HVAC (Hungary)' })).toBeVisible({ timeout: 15000 });
      await page.locator('table').waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
    });

    test('should switch tabs and display leads', async ({ page }) => {
      const leadsSection = page.locator('section[aria-label="Leads"]');
      await leadsSection.getByRole('tab', { name: /pending/i }).click();
      await leadsSection.getByRole('tab', { name: /reviewed/i }).click();
      await leadsSection.getByRole('tab', { name: /enrich/i }).click();
      await leadsSection.getByRole('tab', { name: /pending/i }).click();
    });

    test('should switch between campaigns using the top navigation', async ({ page }) => {
      const nav = page.locator('nav[aria-label="Campaigns"]');

      await nav.getByRole('tab', { name: /Eshops|Shoe/i }).click();
      await expect(page.getByRole('heading', { name: /Small Eshops|Shoe/i })).toBeVisible();

      await nav.getByRole('tab', { name: /WP Remediation/i }).click();
      await expect(page.getByRole('heading', { name: /WP Remediation/i })).toBeVisible();

      await nav.getByRole('tab', { name: /JENEX HVAC/i }).click();
      await expect(page.getByRole('heading', { name: 'JENEX HVAC (Hungary)' })).toBeVisible();
    });

    test('should open settings and update business brief', async ({ page }) => {
      await page.locator('button').filter({ has: page.locator('svg.lucide-settings') }).click();
      await expect(page.getByRole('dialog')).toBeVisible();

      const briefTextarea = page.locator('textarea[placeholder*="Describe your business"]');
      await expect(briefTextarea).toBeVisible();
      
      const originalValue = await briefTextarea.inputValue();
      const testValue = originalValue + ' (E2E Test Append)';
      await briefTextarea.fill(testValue);
      
      await page.getByRole('button', { name: /^save$/i }).click();
      await expect(page.getByText(/Saved/i)).toBeVisible({ timeout: 10000 });

      await page.reload();
      await page.locator('button').filter({ has: page.locator('svg.lucide-settings') }).click();
      await expect(briefTextarea).toHaveValue(testValue);

      await briefTextarea.fill(originalValue);
      await page.getByRole('button', { name: /^save$/i }).click();
    });

    test('should open lead drawer and show details', async ({ page }) => {
      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Nothing here yet') || rowText?.includes('Queue is empty') || rowText?.includes('empty.pending') || rowText?.includes('No pending leads')) {
        test.skip(true, 'No pending leads to click');
        return;
      }
      
      await firstRow.locator('td:nth-child(2)').click();

      const drawer = page.getByRole('dialog').filter({ hasText: /Rationale|Odôvodnenie/i });
      await expect(drawer).toBeVisible();

      await expect(drawer.getByText(/Rationale|Odôvodnenie/i)).toBeVisible();
      await expect(drawer.getByText(/Evidence|Dôkazy/i)).toBeVisible();
      
      await page.keyboard.press('Escape');
    });

    test('should approve a lead and move it to Approved tab', async ({ page }) => {
      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Nothing here yet') || rowText?.includes('Queue is empty') || rowText?.includes('empty.pending') || rowText?.includes('No pending leads')) {
        test.skip(true, 'No pending leads to approve');
        return;
      }
      
      const companyName = await firstRow.locator('td').nth(1).textContent() || '';
      
      await firstRow.locator('td:nth-child(2)').click();

      const drawer = page.getByRole('dialog').filter({ hasText: /Rationale|Odôvodnenie/i });
      await expect(drawer).toBeVisible();

      await drawer.getByRole('button', { name: /Approve|Schváliť/i }).click();

      const leadsSection = page.locator('section[aria-label="Leads"]');
      await leadsSection.getByRole('tab', { name: /reviewed/i }).click();
      await expect(page.locator('table tbody').getByText(companyName).first()).toBeVisible();
    });

    test('should filter leads by search query', async ({ page }) => {
      const firstRow = page.locator('table tbody tr').first();
      await firstRow.waitFor({ state: 'visible' });

      const rowText = await firstRow.textContent();
      if (rowText?.includes('Queue is empty') || rowText?.includes('Nothing here yet') || rowText?.includes('empty.pending')) {
        test.skip(true, 'No leads to test search');
        return;
      }

      const companyName = await firstRow.locator('td').nth(1).textContent() || '';
      if (!companyName) return;

      const searchInput = page.getByPlaceholder(/search|dopyt/i);
      await searchInput.fill(companyName);

      await expect(page.locator('table tbody').getByText(companyName).first()).toBeVisible();

      await searchInput.fill('XYZ_NON_EXISTENT_XYZ');
      await expect(page.getByText(/Queue is empty|No reviewed leads|No pending leads|empty\.pending/i)).toBeVisible();

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
  });
});
