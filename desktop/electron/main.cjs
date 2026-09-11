const { app, BrowserWindow, ipcMain, protocol, net, dialog, shell, session } = require('electron');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { StudioService } = require('./studio-service.cjs');
const { runtimeCommand, runBridge } = require('./bridge.cjs');

protocol.registerSchemesAsPrivileged([{ scheme: 'hantek', privileges: { standard: true, secure: true, supportFetchAPI: true } }]);
app.setAppUserModelId('local.hantek.studio');
function locateRepository() {
  const starts = app.isPackaged ? [process.env.PORTABLE_EXECUTABLE_DIR, path.dirname(process.execPath)].filter(Boolean) : [path.resolve(__dirname, '..', '..')];
  for (const start of starts) {
    let candidate = path.resolve(start);
    for (let level = 0; level < 5; level++) {
      if (fs.existsSync(path.join(candidate, 'src', 'hantek_scope.py')) && fs.existsSync(path.join(candidate, 'desktop', 'package.json'))) return candidate;
      candidate = path.dirname(candidate);
    }
  }
  return null;
}
const repoRoot = locateRepository();
const testProfile = process.env.HANTEK_STUDIO_PROFILE;
if (testProfile && path.isAbsolute(testProfile)) app.setPath('userData', testProfile);
else if (repoRoot) app.setPath('userData', path.join(repoRoot, '.local', 'desktop-profile'));

let mainWindow, service, quitWhenIdle = false;
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } });
  app.whenReady().then(start).catch(error => { dialog.showErrorBox('Hantek Studio could not start', String(error.message || error)); app.quit(); });
}

async function start() {
  const dist = path.resolve(__dirname, '..', 'dist');
  protocol.handle('hantek', request => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'app' || request.method !== 'GET') return new Response('Not found', { status: 404 });
      const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html';
      const file = path.resolve(dist, relative);
      if (!file.startsWith(dist + path.sep) || !/\.(?:html|js|css|svg|woff2|png|ico)$/.test(file)) return new Response('Not found', { status: 404 });
      return net.fetch(pathToFileURL(file).href);
    } catch { return new Response('Not found', { status: 404 }); }
  });
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*', 'ws://*/*', 'wss://*/*'] }, (_details, callback) => callback({ cancel: true }));
  const dataDir = process.env.HANTEK_STUDIO_DATA_DIR;
  const storageDir = dataDir && path.isAbsolute(dataDir) ? dataDir : repoRoot ? path.join(repoRoot, 'artifacts') : path.join(app.getPath('documents'), 'Hantek Studio');
  service = new StudioService({ storageDir, settingsPath: path.join(app.getPath('userData'), 'settings.json'), previewDir: path.join(app.getPath('userData'), 'previews'), version: app.getVersion(), bridge: request => runBridge(runtimeCommand({ packaged: app.isPackaged, resourcesPath: process.resourcesPath, repoRoot }), request) });
  await service.initialize();
  if (process.argv.includes('--demo')) await service.updateSettings({ mode: 'demo' });
  mainWindow = new BrowserWindow({ width: 1440, height: 960, minWidth: 980, minHeight: 680, show: false, backgroundColor: '#f4f5f2', title: 'Hantek Studio', icon: path.join(__dirname, '..', 'assets', 'icon.png'), autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true, spellcheck: false, devTools: !app.isPackaged } });
  mainWindow.setMenu(null);
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', event => event.preventDefault());
  mainWindow.webContents.on('will-attach-webview', event => event.preventDefault());
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('close', event => {
    if (service.state.busy) { event.preventDefault(); quitWhenIdle = true; service.record('info', 'Finishing the current scope operation before closing.'); service.notify(); }
  });
  service.on('state', state => {
    if (!mainWindow.isDestroyed()) mainWindow.webContents.send('scope:state', state);
    if (quitWhenIdle && !state.busy) { quitWhenIdle = false; app.quit(); }
  });
  const register = (name, handler) => ipcMain.handle(`scope:${name}`, (event, ...args) => {
    if (event.sender !== mainWindow.webContents || event.senderFrame !== mainWindow.webContents.mainFrame || !event.senderFrame.url.startsWith('hantek://app/')) throw new Error('Untrusted application request.');
    return handler(...args);
  });
  for (const method of ['getState', 'connect', 'disconnect', 'checkConnection', 'capture', 'setAcquisition', 'panelAction', 'readSettings', 'updateSettings', 'listCaptures', 'updateCapture']) register(method, (...args) => service[method](...args));
  register('chooseStorageDirectory', async () => {
    if (service.state.busy) throw new Error('Wait for the scope operation to finish.');
    const result = await dialog.showOpenDialog(mainWindow, { title: 'Choose capture folder', defaultPath: service.state.settings.storageDir, properties: ['openDirectory', 'createDirectory'] });
    return result.canceled ? service.getState() : service.setStorageDirectory(result.filePaths[0]);
  });
  register('exportCapture', async id => {
    const file = await service.getCaptureFile(id);
    const result = await dialog.showSaveDialog(mainWindow, { title: 'Export capture as PNG', defaultPath: path.basename(file), filters: [{ name: 'PNG image', extensions: ['png'] }] });
    if (result.canceled || !result.filePath) return { cancelled: true };
    if (path.resolve(result.filePath) === path.resolve(file)) return { cancelled: false, path: file };
    // A dialog can stay open while a preview expires; validate again on export.
    await fsp.copyFile(await service.getCaptureFile(id), result.filePath);
    return { cancelled: false, path: result.filePath };
  });
  register('revealCapture', async id => { shell.showItemInFolder(await service.getCaptureFile(id)); });
  register('openStorage', async () => { const error = await shell.openPath(service.state.settings.storageDir); if (error) throw new Error(error); });
  await mainWindow.loadURL('hantek://app/index.html');
}
app.on('window-all-closed', () => app.quit());
