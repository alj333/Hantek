// Explicitly authorized menu-only integration check. Never an offline test.
// Selects exactly one named ordinary menu. Does not retry or restore implicitly.
const { _electron: electron } = require('playwright');
const { expect } = require('@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

(async () => {
  const args = process.argv.slice(2);
  if (args.length !== 3 || args[0] !== '--live' || args[1] !== '--control' || !['ch1-menu', 'trigger-menu'].includes(args[2])) throw new Error('Use --live --control ch1-menu or --live --control trigger-menu for one authorized menu gesture.');
  const control = args[2];
  const repo = path.resolve(__dirname, '..', '..');
  const evidence = path.join(repo, '.local', 'desktop-hardware-menu', randomUUID());
  await fs.mkdir(evidence, { recursive: true });
  const env = { ...process.env, HANTEK_STUDIO_PROFILE: path.join(evidence, 'profile'), HANTEK_STUDIO_DATA_DIR: path.join(repo, 'artifacts') };
  delete env.ELECTRON_RUN_AS_NODE;
  const application = await electron.launch({ executablePath: process.env.HANTEK_TEST_EXECUTABLE || path.join(repo, 'desktop', 'release', 'win-unpacked', 'Hantek Studio.exe'), args: [], env, timeout: 45000 });
  try {
    const page = await application.firstWindow();
    page.setDefaultTimeout(45000);
    await page.getByRole('button', { name: 'Connect scope', exact: true }).click();
    await expect(page.locator('.scope-screen img')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
    await page.locator('.nav-item').filter({ hasText: 'Controls' }).click();
    const before = await page.evaluate(() => window.scopeApp.getState());
    expect(before.appVersion).toBe('0.2.0');
    expect(before.connected).toBe(true);
    expect(before.settings.mode).toBe('hardware');
    const imageBefore = await page.locator('.scope-screen img').getAttribute('src');
    await page.locator(`[data-control-id="${control}"]`).click();
    await expect(page.locator('.last-control-request')).toHaveClass(/replied/, { timeout: 45000 });
    await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
    const state = await page.evaluate(() => window.scopeApp.getState());
    expect(state.connected).toBe(true);
    const imageAfter = await page.locator('.scope-screen img').getAttribute('src');
    for (const [name, data] of [['before', imageBefore], ['after', imageAfter]]) {
      if (!data?.startsWith('data:image/png;base64,')) throw new Error('No scope image was returned.');
      await fs.writeFile(path.join(evidence, `${name}.png`), Buffer.from(data.slice('data:image/png;base64,'.length), 'base64'));
    }
    await page.screenshot({ path: path.join(evidence, 'controls-window.png'), fullPage: true });
    const record = { status: 'exchange_and_preview_passed', appVersion: state.appVersion, packaged: true, control, count: 1, hardwareAccess: true, instrumentStateVerified: false, evidence, note: 'Inspect before.png and after.png separately to verify menu behavior. Original preview wire/JSON records remain under this profile.' };
    await fs.writeFile(path.join(evidence, 'result.json'), JSON.stringify(record, null, 2));
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    console.log(JSON.stringify(record));
  } catch (error) {
    const page = await application.firstWindow();
    await page.screenshot({ path: path.join(evidence, 'failed-window.png'), fullPage: true }).catch(() => {});
    await fs.writeFile(path.join(evidence, 'result.json'), JSON.stringify({ status: 'failed', control, count: 1, instrumentStateVerified: false, error: String(error.message || error), evidence }, null, 2));
    throw error;
  } finally { await application.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
