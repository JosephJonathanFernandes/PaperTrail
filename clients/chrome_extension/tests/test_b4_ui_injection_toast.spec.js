const { test, expect } = require('./fixtures');

test.describe('B4. UI Injection (Toast)', () => {
  test('Test Case 94: Green toast (verified + PDF found)', async ({ page }) => {
    await page.goto('https://example.com');
    // Inject the content scripts manually since extension content scripts might not inject immediately
    await page.addScriptTag({ path: 'content.js' });
    await page.addStyleTag({ path: 'content.css' });
    
    await page.evaluate(() => {
      window.updateToastWithResult({
        status: "success",
        pdf_url: "https://arxiv.org/pdf/1234.pdf",
        metadata: { title: "Test Paper" },
        confidence_tier: "HIGH"
      });
    });

    const toast = page.locator('.papertrail-toast');
    await expect(toast).toBeVisible();
    await expect(toast).toHaveClass(/papertrail-success/);
    await expect(toast).toContainText('Test Paper');
    const link = toast.locator('a');
    await expect(link).toHaveAttribute('href', 'https://arxiv.org/pdf/1234.pdf');
  });

  test('Test Case 95: Orange toast (low-confidence/mismatch flags)', async ({ page }) => {
    await page.goto('https://example.com');
    await page.addScriptTag({ path: 'content.js' });
    await page.addStyleTag({ path: 'content.css' });
    
    await page.evaluate(() => {
      window.updateToastWithResult({
        status: "success",
        pdf_url: "https://arxiv.org/pdf/1234.pdf",
        metadata: { title: "Test Paper" },
        confidence_tier: "LOW",
        flags: ["Author mismatch"]
      });
    });

    const toast = page.locator('.papertrail-toast');
    await expect(toast).toBeVisible();
    await expect(toast).toHaveClass(/papertrail-warning/);
    await expect(toast).toContainText('Author mismatch');
  });

  test('Test Case 96: Red toast (unverified/hallucinated)', async ({ page }) => {
    await page.goto('https://example.com');
    await page.addScriptTag({ path: 'content.js' });
    await page.addStyleTag({ path: 'content.css' });
    
    await page.evaluate(() => {
      window.updateToastWithResult({
        status: "unverified"
      });
    });

    const toast = page.locator('.papertrail-toast');
    await expect(toast).toBeVisible();
    await expect(toast).toHaveClass(/papertrail-error/);
    await expect(toast).toContainText('Unverified Citation');
  });

  test('Test Case 100: Toast auto-dismiss timing / manual close button', async ({ page }) => {
    await page.goto('https://example.com');
    await page.addScriptTag({ path: 'content.js' });
    await page.addStyleTag({ path: 'content.css' });
    
    await page.evaluate(() => {
      window.injectToast("Loading...", "loading");
    });

    const toast = page.locator('.papertrail-toast');
    await expect(toast).toBeVisible();
    
    const closeBtn = toast.locator('.papertrail-close');
    await closeBtn.click();
    await expect(toast).not.toBeVisible();
  });
});
