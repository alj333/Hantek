// Deliberate, opt-in validation. Never part of npm test or the offline build.
// Connect reads identity and a preview; Save capture sends one more screenshot.
// No acquisition, driver, firmware, DUT or CNC operation is issued.
const { _electron: electron } = require('playwright');
const { expect } = require('@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

(async () => {
  if (!process.argv.includes('--live')) throw new Error('Explicit --live is required to inspect the connected oscilloscope.');
  const repo = path.resolve(__dirname, '..', '..');
  const evidence = path.join(repo, '.local', 'desktop-hardware-check', randomUUID());
  await fs.mkdir(evidence, { recursive: true });
  const env = { ...process.env, HANTEK_STUDIO_PROFILE: path.join(evidence, 'profile'), HANTEK_STUDIO_DATA_DIR: path.join(repo, 'artifacts') };
  delete env.ELECTRON_RUN_AS_NODE;
  const executable = process.env.HANTEK_TEST_EXECUTABLE || path.join(repo, 'desktop', 'release', 'win-unpacked', 'Hantek Studio.exe');
  const application = await electron.launch({ executablePath: executable, args: [], env, timeout: 45000 });
  try {
    const page = await application.firstWindow();
    page.setDefaultTimeout(45000);
    await page.getByRole('button', { name: 'Connect scope', exact: true }).click();
    await expect(page.locator('.scope-screen img')).toBeVisible({ timeout: 45000 });
    await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
    const before = await page.evaluate(() => window.scopeApp.getState());
    expect(before.connected).toBe(true); expect(before.settings.mode).toBe('hardware');
    expect(before.device.vid).toBe('049F'); expect(before.device.pid).toBe('505A');
    await page.getByRole('button', { name: 'Save capture', exact: true }).click();
    await expect.poll(async () => (await page.evaluate(() => window.scopeApp.getState())).captures.length, { timeout: 45000 }).toBe(before.captures.length + 1);
    await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
    const state = await page.evaluate(() => window.scopeApp.getState());
    const capture = state.captures.find(item => !before.captures.some(old => old.id === item.id));
    expect(capture.source).toBe('hardware'); expect(capture.checksumVerified).toBe(true);
    await page.screenshot({ path: path.join(evidence, 'hardware-workspace.png'), fullPage: true });
    const report = { status: 'passed', appVersion: state.appVersion, packaged: true, commands: ['identify', 'screenshot', 'screenshot'], acquisitionCommands: 0, captureId: capture.id, createdAt: capture.createdAt, width: capture.width, height: capture.height, checksumVerified: capture.checksumVerified, evidence };
    await fs.writeFile(path.join(evidence, 'result.json'), JSON.stringify(report, null, 2));
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    console.log(JSON.stringify(report));
  } finally { await application.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
