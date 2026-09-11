// Real renderer with a test-only mocked preload. All captures come from demo;
// this window has no IPC bridge to the instrument service.
const { _electron: electron } = require('playwright');
const { expect } = require('@playwright/test');
const path = require('node:path');
const fs = require('node:fs/promises');
const { randomUUID } = require('node:crypto');

(async () => {
  const repo = path.resolve(__dirname, '..', '..');
  const folder = path.join(repo, '.local', 'desktop-preview-ui-tests', randomUUID());
  await fs.mkdir(folder, { recursive: true });
  const env = { ...process.env, HANTEK_STUDIO_PROFILE: path.join(folder, 'profile'), HANTEK_STUDIO_DATA_DIR: path.join(folder, 'data') };
  delete env.ELECTRON_RUN_AS_NODE;
  const packaged = process.env.HANTEK_TEST_EXECUTABLE;
  const application = await electron.launch({ executablePath: packaged || require('electron'), args: [...(packaged ? [] : [path.join(repo, 'desktop')]), '--demo'], env, timeout: 45000 });
  let checks = 0;
  const errors = [];
  try {
    const initialPage = await application.firstWindow();
    await expect(initialPage.getByRole('heading', { name: 'Scope workspace', exact: true })).toBeVisible();
    const fixtures = await initialPage.evaluate(async () => {
      await window.scopeApp.connect();
      const oldCapture = await window.scopeApp.capture({ save: true });
      const freshCapture = await window.scopeApp.capture({ save: false });
      const state = await window.scopeApp.getState();
      return { state, oldCapture, freshCapture };
    });
    expect(fixtures.state.settings.mode).toBe('demo');
    expect(fixtures.oldCapture.source).toBe('demo');
    expect(fixtures.freshCapture.source).toBe('demo');
    const preloadPath = path.join(folder, 'mock-preload.cjs');
    await fs.writeFile(preloadPath, `
const { contextBridge } = require('electron');
const fixtures = ${JSON.stringify(fixtures)};
let state = structuredClone(fixtures.state);
let captureWaiter;
let captureCalls = 0;
const listeners = new Set();
const emit = () => { for (const listener of listeners) listener(structuredClone(state)); };
const freshCapture = () => ({ ...structuredClone(fixtures.freshCapture), createdAt: new Date().toISOString() });
const disconnect = () => { state.connected = false; state.device = null; emit(); return structuredClone(state); };
contextBridge.exposeInMainWorld('scopeApp', {
  getState: async () => structuredClone(state),
  connect: async () => { state.connected = true; state.device = fixtures.state.device; emit(); return structuredClone(state); },
  disconnect: async () => disconnect(),
  capture: async () => {
    if (captureCalls++ === 0) return { ...structuredClone(fixtures.oldCapture), saved: false, createdAt: new Date().toISOString() };
    return new Promise(resolve => { captureWaiter = resolve; });
  },
  panelAction: async () => { disconnect(); return { message: 'Measure requested. Screen refresh failed. The control result is unverified.', capture: null }; },
  setAcquisition: async () => ({ message: 'Run requested. Screen refresh failed. Acquisition result is unverified.', capture: null }),
  updateSettings: async patch => { state.settings = { ...state.settings, ...patch }; return disconnect(); },
  listCaptures: async () => structuredClone(state.captures),
  onStateChanged: callback => { listeners.add(callback); return () => listeners.delete(callback); },
});
contextBridge.exposeInMainWorld('previewTest', {
  releaseCapture: () => { if (!captureWaiter) throw new Error('No capture pending'); const resolve = captureWaiter; captureWaiter = null; resolve(freshCapture()); },
  capturePending: () => Boolean(captureWaiter),
});
`);
    const pagePromise = application.waitForEvent('window');
    await application.evaluate(async ({ BrowserWindow }, preload) => {
      const window = new BrowserWindow({ width: 1200, height: 850, show: true, webPreferences: { preload, contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true } });
      window.setMenu(null);
      await window.loadURL('hantek://app/index.html');
    }, preloadPath);
    const page = await pagePromise;
    page.on('pageerror', error => errors.push(error.message));
    page.setDefaultTimeout(15000);
    const screen = page.locator('.screen-shell');
    await expect(page.getByRole('heading', { name: 'Scope workspace', exact: true })).toBeVisible();
    await expect(screen).toHaveAttribute('data-preview-invalidated', 'true');
    await page.getByRole('button', { name: 'Controls', exact: true }).click();
    await page.getByRole('button', { name: 'Refresh preview', exact: true }).click();
    await expect(screen).toHaveAttribute('data-preview-invalidated', 'false');
    await expect(page.locator('.scope-screen img')).toHaveAttribute('src', fixtures.oldCapture.imageUrl); checks++;

    await page.getByRole('button', { name: 'Measure', exact: true }).click();
    await expect(page.locator('.last-control-request')).toHaveClass(/unconfirmed/);
    await expect(page.getByRole('alert')).toContainText('unverified');
    await expect(screen).toHaveAttribute('data-preview-invalidated', 'true');
    await expect(screen).toHaveAttribute('data-stale', 'true');
    await expect(screen).toContainText('PREVIOUS SCREEN'); checks++;

    await page.getByRole('button', { name: 'Connect demo', exact: true }).click();
    await expect.poll(() => page.evaluate(() => window.previewTest.capturePending())).toBe(true);
    await expect(screen).toHaveAttribute('data-preview-invalidated', 'true');
    await expect(screen).toHaveAttribute('data-stale', 'true');
    await expect(page.locator('.screen-led')).not.toHaveClass(/ready/);
    await expect(page.locator('.scope-screen img')).toHaveAttribute('src', fixtures.oldCapture.imageUrl); checks++;
    await page.screenshot({ path: path.join(folder, 'reconnect-awaiting-fresh-screen.png'), fullPage: true });

    await page.evaluate(() => window.previewTest.releaseCapture());
    await expect(screen).toHaveAttribute('data-preview-invalidated', 'false');
    await expect(screen).toHaveAttribute('data-stale', 'false');
    await expect(page.locator('.scope-screen img')).toHaveAttribute('src', fixtures.freshCapture.imageUrl);
    await expect(page.locator('.screen-led')).toHaveClass(/ready/); checks++;

    await page.getByRole('button', { name: 'Run', exact: true }).click();
    await expect(screen).toHaveAttribute('data-preview-invalidated', 'true');
    await expect(screen).toHaveAttribute('data-stale', 'true');
    await expect(screen).toContainText('PREVIOUS SCREEN'); checks++;

    await page.getByRole('button', { name: 'Settings', exact: true }).click();
    await page.getByRole('button', { name: /USB instrument/ }).click();
    await page.getByRole('button', { name: 'Controls', exact: true }).click();
    await expect(page.locator('.last-control-request')).toHaveClass(/empty/);
    await expect(page.locator('.last-control-request')).not.toContainText('Measure');
    expect(errors).toEqual([]); checks++;
    const result = { status: 'passed', checks, packaged: Boolean(packaged), hardwareAccess: false, mockedInstrumentApi: true, consoleErrors: errors, folder };
    await fs.writeFile(path.join(folder, 'result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally { await application.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
