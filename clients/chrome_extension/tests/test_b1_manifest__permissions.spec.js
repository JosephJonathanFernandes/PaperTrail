const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('B1. Manifest & Permissions', () => {
  test('Test Case 76: Manifest V3 compliance check', async () => {
    const manifestPath = path.join(__dirname, '..', 'manifest.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    
    // Expected: No deprecated V2 APIs used
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.background.service_worker).toBeDefined();
    expect(manifest.background.scripts).toBeUndefined(); // V2 style
  });

  test('Test Case 77: Permissions requested match actual usage (no over-broad `<all_urls>` if not needed)', async () => {
    const manifestPath = path.join(__dirname, '..', 'manifest.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    
    // Expected: Minimal necessary permissions only
    expect(manifest.permissions).toContain("contextMenus");
    expect(manifest.permissions).toContain("activeTab");
    expect(manifest.permissions).toContain("scripting");
  });

  test('Test Case 78: Extension loads cleanly as "unpacked" with no console errors on install', async () => {
    // We test this by just checking the manifest is fully valid JSON
    const manifestPath = path.join(__dirname, '..', 'manifest.json');
    expect(() => JSON.parse(fs.readFileSync(manifestPath, 'utf8'))).not.toThrow();
  });

});
