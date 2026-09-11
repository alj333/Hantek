// Actual Electron renderer and IPC, always isolated demo mode; no USB access.
const { _electron: electron } = require('playwright');
const { expect } = require('@playwright/test');
const path = require('node:path');
const fs = require('node:fs/promises');
const { randomUUID } = require('node:crypto');

(async () => {
  const repo = path.resolve(__dirname, '..', '..');
  const folder = path.join(repo, '.local', 'desktop-controls-ui-tests', randomUUID());
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
    args: [...(packaged ? [] : [path.join(repo, 'desktop')]), '--demo'],
    env,
    timeout: 45000,
  });
  const errors = [];
  let checks = 0;
  try {
    const page = await application.firstWindow();
    page.on('pageerror', error => errors.push(error.message));
    page.setDefaultTimeout(15000);
    await expect(page.getByRole('heading', { name: 'Scope workspace', exact: true })).toBeVisible();
    const initial = await page.evaluate(() => window.scopeApp.getState());
    expect(initial.settings.mode).toBe('demo');
    expect(initial.connected).toBe(false);
    expect(initial.controlCatalog.length).toBeGreaterThan(0);
    const button = initial.controlCatalog.find(control => control.kind === 'button');
    const rotary = initial.controlCatalog.find(control => control.kind === 'rotary' && /time\/div/i.test(control.label));
    const menu = initial.controlCatalog.find(control => control.kind === 'button' && /menu/i.test(control.group));
    const softkey = initial.controlCatalog.find(control => control.kind === 'button' && /soft.?key|soft key|screen key/i.test(`${control.group} ${control.label} ${control.description}`));
    expect(button).toBeTruthy(); expect(rotary).toBeTruthy();
    expect(menu).toBeTruthy(); expect(softkey).toBeTruthy(); checks++;

    await page.getByRole('button', { name: 'Controls', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Front-panel controls', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: button.label, exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: rotary.label, exact: true })).toBeDisabled(); checks++;
    await page.getByRole('button', { name: 'Connect demo', exact: true }).click();
    await expect(page.getByRole('button', { name: button.label, exact: true })).toBeEnabled();
    await expect(page.locator('.scope-screen img')).toBeVisible(); checks++;

    const result = page.getByRole('region', { name: 'Last control request', exact: true });
    for (const control of [menu, softkey]) {
      await page.getByRole('button', { name: control.label, exact: true }).click();
      await expect(result).toContainText(control.label);
      await expect(result).toContainText(/demo|simulated/i);
      await expect(page.getByRole('button', { name: control.label, exact: true })).toBeEnabled();
    }
    expect((await page.evaluate(() => window.scopeApp.getState())).captures).toHaveLength(0); checks++;

    const steps = page.getByLabel('Rotary steps per click', { exact: true });
    await expect(steps).toHaveAttribute('min', '1');
    await expect(steps).toHaveAttribute('max', '5');
    for (const invalid of ['0', '6', '1.5']) {
      await steps.fill(invalid);
      await expect(page.getByRole('button', { name: rotary.label, exact: true })).toBeDisabled();
      await expect(page.getByText('Use 1–5 whole steps.', { exact: true })).toBeVisible();
    }
    await steps.fill('5');
    await expect(page.getByRole('button', { name: rotary.label, exact: true })).toBeEnabled();
    await page.getByRole('button', { name: rotary.label, exact: true }).click();
    await expect(result).toContainText(rotary.label);
    await expect(result).toContainText(/5/);
    await expect(result).toContainText(/demo|simulated/i); checks++;

    // Rotary repeat must never turn a menu button into repeated presses.
    await page.getByRole('button', { name: menu.label, exact: true }).click();
    await expect(result).toContainText(menu.label);
    await expect(result).not.toContainText('5 steps');
    await expect(page.getByRole('button', { name: menu.label, exact: true })).toBeEnabled();
    const actionLogs = await fs.readdir(path.join(folder, 'data', 'demo', 'logs'));
    const menuRecords = await Promise.all(actionLogs.filter(name => /^panel-.*\.json$/.test(name))
      .map(async name => JSON.parse(await fs.readFile(path.join(folder, 'data', 'demo', 'logs', name), 'utf8'))));
    expect(menuRecords.filter(record => record.control === menu.id).every(record => record.count === 1)).toBe(true); checks++;

    await page.getByRole('button', { name: 'Save settings record', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Save settings record', exact: true })).toBeEnabled();
    await expect.poll(async () => (await fs.readdir(path.join(folder, 'data', 'demo', 'logs')))
      .filter(name => /^settings-.*\.json$/.test(name)).length).toBeGreaterThan(0); checks++;

    const invalidRequest = await page.evaluate(async () => {
      try { await window.scopeApp.panelAction({ control: 'factory-reset', count: 1 }); return { accepted: true }; }
      catch (error) { return { accepted: false, message: String(error.message || error) }; }
    });
    expect(invalidRequest.accepted).toBe(false);
    expect((await page.evaluate(() => window.scopeApp.getState())).settings.mode).toBe('demo'); checks++;

    await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1000, 740));
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await expect(page.getByRole('heading', { name: 'Front-panel controls', exact: true })).toBeVisible();
    await page.screenshot({ path: path.join(folder, 'compact-controls.png'), fullPage: true }); checks++;

    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    await expect(page.getByRole('button', { name: button.label, exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: rotary.label, exact: true })).toBeDisabled();
    expect(errors).toEqual([]); checks++;
    const finalState = await page.evaluate(() => window.scopeApp.getState());
    expect(finalState.connected).toBe(false);
    expect(finalState.settings.mode).toBe('demo');
    expect(finalState.captures).toHaveLength(0);
    const resultRecord = { status: 'passed', checks, packaged: Boolean(packaged), hardwareAccess: false, consoleErrors: errors };
    await fs.writeFile(path.join(folder, 'result.json'), JSON.stringify(resultRecord, null, 2));
    console.log(JSON.stringify({ ...resultRecord, folder }));
  } finally { await application.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
