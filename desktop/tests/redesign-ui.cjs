// Visual/functional regression of the real Electron app with isolated demo data.
// Native file actions are checked without opening dialogs; hardware is never selected.
const { _electron: electron } = require('playwright');
const { expect } = require('@playwright/test');
const path = require('node:path');
const fs = require('node:fs/promises');
const { randomUUID } = require('node:crypto');

(async () => {
  const repo = path.resolve(__dirname, '..', '..');
  const folder = path.join(repo, '.local', 'desktop-redesign-ui-tests', randomUUID());
  await fs.mkdir(folder, { recursive: true });
  const env = {
    ...process.env,
    HANTEK_STUDIO_PROFILE: path.join(folder, 'profile'),
    HANTEK_STUDIO_DATA_DIR: path.join(folder, 'data'),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const packaged = process.env.HANTEK_TEST_EXECUTABLE;
  const application = await electron.launch({
    executablePath: packaged || require('electron'),
    // The other native suites retain the host display scaling. This visual
    // suite uses 1:1 scaling so odd reference dimensions survive Windows DIP
    // rounding and screenshots remain reproducible across display setups.
    args: [...(packaged ? [] : [path.join(repo, 'desktop')]), '--demo', '--force-device-scale-factor=1'],
    env,
    timeout: 45000,
  });
  const errors = [];
  const checks = [];
  const screenshots = [];
  try {
    const page = await application.firstWindow();
    page.on('pageerror', error => errors.push(error.message));
    page.setDefaultTimeout(15000);
    const nav = page.getByRole('navigation', { name: 'Main navigation' });
    const state = () => page.evaluate(() => window.scopeApp.getState());
    const navigate = async (name) => {
      // Captures includes the saved-record count in its accessible name.
      const item = nav.getByRole('button', { name: new RegExp(`^${name}(?:\\s*\\d+)?$`) });
      // Exercise keyboard navigation, including its focusable native button.
      await item.focus();
      await expect(item).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(item).toHaveAttribute('aria-current', 'page');
      await expect(page.locator('main h1')).toHaveCount(1);
    };
    const noOverflow = async () => {
      await expect.poll(() => page.evaluate(() => ({
        document: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        body: document.body.scrollWidth <= document.documentElement.clientWidth + 1,
      }))).toEqual({ document: true, body: true });
    };
    const screenshot = async (name) => {
      await noOverflow();
      const filename = `${name}.png`;
      await page.screenshot({ path: path.join(folder, filename), scale: 'css' });
      screenshots.push({ filename, viewport: await page.evaluate(() => ({ width: innerWidth, height: innerHeight })) });
    };
    const screenFits = async () => {
      await page.evaluate(() => window.scrollTo(0, 0));
      await expect.poll(() => page.locator('.scope-screen').evaluate(element => {
        const box = element.getBoundingClientRect();
        return box.top >= 0 && box.left >= 0 && box.right <= innerWidth + 1 && box.bottom <= innerHeight + 1;
      })).toBe(true);
      const image = page.locator('.scope-screen img');
      await expect(image).toBeVisible();
      await expect(page.locator('.screen-shell')).toHaveAttribute('data-preview-invalidated', 'false');
      expect(await image.evaluate(element => ({ width: element.naturalWidth, height: element.naturalHeight, fit: getComputedStyle(element).objectFit })))
        .toEqual({ width: 800, height: 480, fit: 'contain' });
    };

    await expect(page.getByRole('heading', { name: 'Scope workspace', exact: true })).toBeVisible();
    const initial = await state();
    expect(initial.settings.mode).toBe('demo');
    expect(initial.connected).toBe(false);
    expect(initial.captures).toHaveLength(0);
    await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeDisabled();
    await expect(page.getByRole('switch')).not.toBeChecked();
    const boundary = await page.evaluate(() => ({ require: typeof window.require, process: typeof window.process }));
    expect(boundary).toEqual({ require: 'undefined', process: 'undefined' });
    const security = await application.evaluate(({ BrowserWindow }) => {
      const preferences = BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();
      return { contextIsolation: preferences.contextIsolation, sandbox: preferences.sandbox, nodeIntegration: preferences.nodeIntegration };
    });
    expect(security).toEqual({ contextIsolation: true, sandbox: true, nodeIntegration: false });
    const fontState = await page.evaluate(async () => {
      await document.fonts.ready;
      return { loaded: document.fonts.check('500 13px InterVariable'), faces: [...document.fonts].map(font => ({ family: font.family, status: font.status })) };
    });
    expect(fontState.loaded).toBe(true);
    expect(fontState.faces.some(font => font.family.replaceAll('"', '') === 'InterVariable' && font.status === 'loaded')).toBe(true);
    checks.push('isolated demo startup retains sandbox and disconnected defaults');

    const minimum = await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getMinimumSize());
    const sizes = [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'minimum', width: minimum[0], height: minimum[1] }];
    expect(minimum[0]).toBeGreaterThan(0); expect(minimum[1]).toBeGreaterThan(0);
    for (const size of sizes) {
      await application.evaluate(({ BrowserWindow }, dimensions) => {
        const window = BrowserWindow.getAllWindows()[0];
        window.setSize(dimensions.width, dimensions.height);
      }, size);
      await navigate('Workspace');
      if (!(await state()).connected) await page.getByRole('button', { name: 'Connect demo', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
      await screenFits();
      await expect(page.locator('.screen-shell')).toContainText('DEMO');
      await screenshot(`${size.name}-workspace`);
      checks.push(`${size.name}: full uncropped screen and demo source remain visible`);

      const beforeRefresh = await page.locator('.scope-screen img').getAttribute('src');
      const savedBeforeRefresh = (await state()).captures.length;
      await page.getByRole('switch').check();
      await page.getByRole('button', { name: 'Refresh preview', exact: true }).click();
      await expect(page.getByRole('switch')).not.toBeChecked();
      await expect.poll(() => page.locator('.scope-screen img').getAttribute('src')).not.toBe(beforeRefresh);
      expect((await state()).captures).toHaveLength(savedBeforeRefresh);
      await page.getByRole('switch').check();
      await page.getByRole('button', { name: 'Open controls', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Front-panel controls', exact: true })).toBeVisible();
      await navigate('Workspace');
      await expect(page.getByRole('switch')).not.toBeChecked();
      await navigate('Controls');
      checks.push(`${size.name}: new preview and controls shortcuts stop automatic refresh without saving`);
      await expect(page.getByLabel('Rotary steps per click', { exact: true })).toBeEnabled();
      const catalog = (await state()).controlCatalog;
      expect(catalog.length).toBeGreaterThan(0);
      const renderedIds = await page.locator('[data-control-id]').evaluateAll(elements => elements.map(element => element.getAttribute('data-control-id')));
      expect(renderedIds.slice().sort()).toEqual(catalog.map(control => control.id).sort());
      // A trial click scrolls each button into its actual visible scroll region,
      // checks overlap/actionability, and does not dispatch a scope request.
      for (const control of catalog) {
        const matching = page.locator(`[data-control-id=${JSON.stringify(control.id)}]`);
        await expect(matching).toHaveCount(1);
        await expect(matching).toHaveAccessibleName(control.label);
        await expect(matching).toHaveAttribute('data-validation', control.validation);
        await matching.click({ trial: true });
      }
      await page.evaluate(() => {
        window.scrollTo(0, 0);
        for (const element of document.querySelectorAll('.control-groups')) element.scrollTop = 0;
      });
      await screenFits();
      await expect(page.getByRole('group', { name: 'Right-screen softkeys', exact: true })).toBeVisible();
      await screenshot(`${size.name}-controls`);
      checks.push(`${size.name}: every advertised panel control is reachable and labelled`);

      const rotary = catalog.find(control => control.kind === 'rotary' && /time\/div/i.test(control.label));
      expect(rotary).toBeTruthy();
      await page.getByLabel('Rotary steps per click', { exact: true }).fill('1');
      await page.getByRole('button', { name: rotary.label, exact: true }).click();
      await expect(page.getByRole('region', { name: 'Last control request', exact: true })).toContainText(rotary.label);
      await expect(page.getByRole('region', { name: 'Last control request', exact: true })).toContainText(/demo|simulated/i);
      await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
      await page.getByRole('button', { name: 'Save capture', exact: true }).click();
      const expectedCount = sizes.indexOf(size) + 1;
      await expect.poll(async () => (await state()).captures.length).toBe(expectedCount);
      checks.push(`${size.name}: relative control refresh and explicit saved capture work`);

      await navigate('Captures');
      await expect(page.locator('.capture-card')).toHaveCount(expectedCount);
      await page.locator('.capture-card').first().click();
      const title = `Redesign ${size.name} demo record`;
      await page.getByLabel('Capture name', { exact: true }).fill(title);
      await page.getByLabel('Notes', { exact: true }).fill('Synthetic demo screen. No instrument or measured circuit was accessed.');
      await page.getByRole('button', { name: 'Save details', exact: true }).click();
      await expect(page.locator('.capture-card h3').first()).toHaveText(title);
      await page.getByLabel('Search captures', { exact: true }).fill(title);
      await expect(page.locator('.capture-card')).toHaveCount(1);
      await page.getByLabel('Search captures', { exact: true }).fill('');
      await page.getByRole('button', { name: 'Export PNG', exact: true }).click({ trial: true });
      await page.evaluate(() => window.scrollTo(0, 0));
      await screenshot(`${size.name}-capture-details`);
      checks.push(`${size.name}: capture details, source, search and export remain accessible`);

      await navigate('Workspace');
      await page.locator('.recent-capture-link').click();
      await expect(page.getByLabel('Capture name', { exact: true })).toHaveValue(title);
      const latestCapture = (await state()).captures.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
      expect(latestCapture.label).toBe(title);
      await expect(page.locator('.detail-image img')).toHaveAttribute('src', latestCapture.imageUrl);
      checks.push(`${size.name}: recent-capture shortcut opens the latest saved record`);

      await navigate('Settings');
      await expect(page.getByRole('heading', { name: 'Workspace settings', exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Advanced connection', exact: true }).click();
      await expect(page.getByLabel('Device interface GUID', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Advanced connection', exact: true }).click();
      await page.getByLabel('Auto-refresh interval').selectOption(size.name === 'desktop' ? '3000' : '5000');
      await expect(page.getByRole('button', { name: 'Connect demo', exact: true })).toBeEnabled();
      expect((await state()).connected).toBe(false);
      await page.evaluate(() => window.scrollTo(0, 0));
      await screenshot(`${size.name}-settings`);
      await navigate('Workspace');
      await expect(page.getByRole('switch')).not.toBeChecked();
      checks.push(`${size.name}: keyboard navigation and preference changes retain disconnect semantics`);
    }

    // Match the actual generated reference dimensions, not an assumed 1440-wide
    // image. Use content size because Playwright screenshots exclude OS chrome.
    const reference = await fs.readFile(path.join(repo, 'docs', 'design', '2026-09-12', 'workspace-concept.png'));
    expect(reference.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    const referenceSize = { width: reference.readUInt32BE(16), height: reference.readUInt32BE(20) };
    const requested = { ...referenceSize };
    for (let attempt = 0; attempt < 3; attempt++) {
      await application.evaluate(({ BrowserWindow }, dimensions) => BrowserWindow.getAllWindows()[0].setContentSize(dimensions.width, dimensions.height), requested);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const actual = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
      if (actual.width === referenceSize.width && actual.height === referenceSize.height) break;
      // Windows rounds native DIP sizes at fractional display scaling.
      requested.width += referenceSize.width - actual.width;
      requested.height += referenceSize.height - actual.height;
    }
    await page.getByRole('button', { name: 'Connect demo', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Save capture', exact: true })).toBeEnabled();
    await expect(page.locator('.screen-shell')).toHaveAttribute('data-preview-invalidated', 'false');
    await page.getByRole('button', { name: 'Dismiss message', exact: true }).click();
    await screenFits();
    await screenshot('reference-size-workspace');
    expect(screenshots.at(-1).viewport).toEqual(referenceSize);
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    checks.push('generated-reference dimensions captured with a connected demo and saved records');

    const finalState = await state();
    expect(finalState.settings.mode).toBe('demo');
    expect(finalState.connected).toBe(false);
    expect(finalState.captures.every(capture => capture.source === 'demo' && capture.saved && !capture.checksumVerified)).toBe(true);
    expect(errors).toEqual([]);
    const result = { status: 'passed', checks: checks.length, details: checks, minimumWindow: minimum, screenshots, fontState, packaged: Boolean(packaged), hardwareAccess: false, consoleErrors: errors, folder };
    await fs.writeFile(path.join(folder, 'result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } catch (error) {
    const page = (await application.windows())[0];
    if (page) await page.screenshot({ path: path.join(folder, 'failure.png'), fullPage: true }).catch(() => {});
    await fs.writeFile(path.join(folder, 'result.json'), JSON.stringify({ status: 'failed', checks, error: String(error.stack || error), folder }, null, 2));
    console.error(`Redesign failure evidence: ${folder}`);
    throw error;
  } finally { await application.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
