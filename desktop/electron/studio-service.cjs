const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { EventEmitter } = require('node:events');
const { demoImage } = require('./demo-image.cjs');

const DEFAULT_GUID = '5cb35641-beea-4a98-b06b-3cf4dca1911b';
const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HARDWARE_NAME = /^scope-\d{8}T\d{6}\.\d{6}Z\.json$/;
const DEMO_NAME = /^demo-[a-z0-9-]+\.json$/;

function validateSettingsPatch(patch) {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('Invalid settings.');
  const result = {};
  for (const key of Object.keys(patch)) {
    if (!['mode', 'refreshIntervalMs', 'interfaceGuid'].includes(key)) throw new Error(`Unknown setting: ${key}`);
    const value = patch[key];
    if (key === 'mode' && !['hardware', 'demo'].includes(value)) throw new Error('Choose a USB scope or demo mode.');
    if (key === 'refreshIntervalMs' && (!Number.isInteger(value) || value < 3000 || value > 60000)) throw new Error('Refresh interval must be between 3 and 60 seconds.');
    if (key === 'interfaceGuid' && (typeof value !== 'string' || !GUID_RE.test(value) || /^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(value))) throw new Error('Enter a valid, nonzero interface GUID.');
    result[key] = key === 'interfaceGuid' ? value.toLowerCase() : value;
  }
  return result;
}
function safeDirectory(value) {
  if (typeof value !== 'string' || !path.isAbsolute(value) || value.length > 2000 || value.includes('\0')) throw new Error('Choose an absolute local storage directory.');
  return path.resolve(value);
}
function friendlyError(error) {
  const text = String(error?.message || error).slice(0, 2000);
  if (/found 0|found0|exactly one present.*0/i.test(text)) return 'Scope not found. Check power, USB cable and the configured USB port. The connection needs the WinUSB driver.';
  if (/Cannot open the scope|access.*denied/i.test(text)) return 'The scope is unavailable or in use. Close other scope clients, then reconnect.';
  if (/Unexpected response command: 92/i.test(text)) return 'A pending scope status interrupted the connection test. See the recovery notes; do not reinstall the driver.';
  return text;
}
async function readJson(file, limit = 65536) {
  const stat = await fs.lstat(file);
  if (!stat.isFile() || stat.size > limit) throw new Error('Record is too large.');
  return JSON.parse(await fs.readFile(file, 'utf8'));
}
async function atomicJson(file, value) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temp = `${file}.${randomUUID()}.tmp`;
  await fs.writeFile(temp, JSON.stringify(value, null, 2), { flag: 'wx' });
  try { await fs.rename(temp, file); } catch (error) { await fs.unlink(temp).catch(() => {}); throw error; }
}

class StudioService extends EventEmitter {
  constructor({ storageDir, settingsPath, previewDir, bridge, version = '0.1.0' }) {
    super();
    this.settingsPath = settingsPath;
    this.previewDir = safeDirectory(previewDir);
    this.bridge = bridge;
    this.state = { appVersion: version, settings: { mode: 'hardware', storageDir: safeDirectory(storageDir), refreshIntervalMs: 5000, interfaceGuid: DEFAULT_GUID }, connected: false, busy: false, device: null, captures: [], activity: [] };
    this.registry = new Map();
    this.demoPhase = 0;
    this.demoRunning = true;
  }
  async initialize() {
    try {
      const stored = await readJson(this.settingsPath, 8192);
      const { storageDir, ...settings } = stored;
      this.state.settings = { ...this.state.settings, ...validateSettingsPatch(settings), storageDir: safeDirectory(storageDir) };
    } catch (error) { if (error.code !== 'ENOENT') this.record('info', 'Saved preferences could not be loaded; using defaults.'); }
    await fs.mkdir(this.state.settings.storageDir, { recursive: true });
    await this.refreshLibrary();
    return this.getState();
  }
  getState() { return structuredClone(this.state); }
  notify() { this.emit('state', this.getState()); }
  record(kind, message) {
    this.state.activity.unshift({ id: randomUUID(), at: new Date().toISOString(), kind, message });
    this.state.activity = this.state.activity.slice(0, 40);
  }
  async exclusive(work) {
    if (this.state.busy) throw new Error('A scope operation is already in progress. Wait for it to finish.');
    this.state.busy = true; this.notify();
    try { return await work(); }
    catch (error) { const message = friendlyError(error); this.record('error', message); throw new Error(message); }
    finally { this.state.busy = false; this.notify(); }
  }
  requireConnection() { if (!this.state.connected) throw new Error('Connect to the scope first.'); }
  async call(action, extra = {}) {
    try { return await this.bridge({ action, guid: this.state.settings.interfaceGuid, ...extra }); }
    catch (error) { this.state.connected = false; this.state.device = null; throw error; }
  }
  async connect() {
    await this.exclusive(async () => {
      this.state.connected = false; this.state.device = null;
      if (this.state.settings.mode === 'hardware') {
        const identity = await this.call('identify');
        if (identity.vid?.toUpperCase() !== '049F' || identity.pid?.toUpperCase() !== '505A') throw new Error('The connected USB device is not the configured scope.');
        this.state.device = { model: 'Hantek DSO5102P', vid: '049F', pid: '505A' };
      } else this.state.device = { model: 'Demo oscilloscope', vid: 'DEMO', pid: 'DEMO' };
      this.state.connected = true;
      this.record('success', this.state.settings.mode === 'demo' ? 'Demo connected. All displayed signals are simulated.' : 'Hantek DSO5102P connected through USB.');
    });
    return this.getState();
  }
  async disconnect() {
    await this.exclusive(async () => { this.state.connected = false; this.state.device = null; this.record('info', 'Disconnected. The scope acquisition state was left unchanged.'); });
    return this.getState();
  }
  async checkConnection() {
    return this.exclusive(async () => {
      this.requireConnection();
      if (this.state.settings.mode === 'hardware') {
        const response = await this.call('echo');
        if (response.echo !== 'ok') throw new Error('The connection test did not return a matching echo.');
      }
      const message = this.state.settings.mode === 'demo' ? 'Demo connection test passed. No USB access.' : 'USB round-trip check passed.';
      this.record('success', message); return { message };
    });
  }
  async updateSettings(patch) {
    const validated = validateSettingsPatch(patch);
    await this.exclusive(async () => {
      const next = { ...this.state.settings, ...validated };
      await atomicJson(this.settingsPath, next);
      this.state.settings = next; this.state.connected = false; this.state.device = null;
      this.record('info', 'Preferences saved. Reconnect to start a new session.');
    });
    return this.getState();
  }
  async setStorageDirectory(directory) {
    const storageDir = safeDirectory(directory);
    await this.exclusive(async () => {
      await fs.mkdir(storageDir, { recursive: true });
      const probe = path.join(storageDir, `.hantek-write-check-${randomUUID()}`);
      await fs.writeFile(probe, '', { flag: 'wx' }); await fs.unlink(probe);
      const next = { ...this.state.settings, storageDir };
      await atomicJson(this.settingsPath, next);
      this.state.settings = next; this.state.connected = false; this.state.device = null;
      await this.refreshLibrary(); this.record('info', 'Capture folder changed. Existing captures remain in their original folder.');
    });
    return this.getState();
  }
  async capture(options = {}) {
    if (!options || typeof options !== 'object' || Array.isArray(options) || Object.keys(options).some(key => key !== 'save') || ('save' in options && typeof options.save !== 'boolean')) throw new Error('Invalid capture options.');
    return this.exclusive(async () => { this.requireConnection(); return this.captureInternal(options.save !== false); });
  }
  async captureInternal(save) {
    const source = this.state.settings.mode;
    const directory = save
      ? path.join(this.state.settings.storageDir, ...(source === 'demo' ? ['demo', 'captures'] : ['captures']))
      : path.join(this.previewDir, randomUUID());
    await fs.mkdir(directory, { recursive: true });
    let metadata, file;
    if (source === 'demo') {
      if (this.demoRunning) this.demoPhase += 0.18;
      const stem = `demo-${Date.now()}-${randomUUID()}`;
      file = path.join(directory, `${stem}.json`);
      await fs.writeFile(path.join(directory, `${stem}.png`), demoImage(this.demoPhase), { flag: 'wx' });
      metadata = { status: 'complete', width: 800, height: 480, source: 'demo', started_utc: new Date().toISOString(), png_path: path.join(directory, `${stem}.png`), generated: true };
      await atomicJson(file, metadata);
    } else {
      metadata = await this.call('screenshot', { output_dir: directory });
      // Never trust an arbitrary output path reported by a child process.
      const name = path.basename(String(metadata.png_path || '')).replace(/\.png$/, '.json');
      if (!HARDWARE_NAME.test(name) || path.dirname(path.resolve(metadata.png_path)) !== path.resolve(directory)) throw new Error('The scope returned an unexpected capture path.');
      file = path.join(directory, name);
    }
    const capture = await this.readCapture(file, source, save);
    if (save) {
      await this.refreshLibrary(); this.record('success', source === 'demo' ? 'Demo capture saved.' : 'Scope capture saved with verified checksums.');
    } else await this.prunePreviews(directory);
    return capture;
  }
  async setAcquisition(action) {
    if (!['start', 'stop'].includes(action)) throw new Error('Choose start or stop acquisition.');
    return this.exclusive(async () => {
      this.requireConnection();
      let message;
      if (this.state.settings.mode === 'demo') {
        this.demoRunning = action === 'start'; message = `Demo acquisition ${action === 'start' ? 'started' : 'stopped'}.`;
      } else {
        await this.call(`acquisition-${action}`, { log_dir: path.join(this.state.settings.storageDir, 'logs') });
        message = `${action === 'start' ? 'Run' : 'Stop'} requested. Check the scope screen to confirm acquisition state.`;
      }
      this.record('info', message);
      try { return { message, capture: await this.captureInternal(false) }; }
      catch (error) {
        const failure = `${message} Screen refresh failed: ${friendlyError(error)} Acquisition result is unverified; do not automatically retry.`;
        this.record('error', failure); return { message: failure, capture: null };
      }
    });
  }
  async readCapture(file, source, saved) {
    const name = path.basename(file);
    if (!(source === 'demo' ? DEMO_NAME : HARDWARE_NAME).test(name)) throw new Error('Unrecognized capture record.');
    const meta = await readJson(file);
    if (Object.hasOwn(meta, 'error') || meta.status !== 'complete' || meta.width !== 800 || meta.height !== 480) throw new Error('Capture is incomplete. Its partial evidence has been retained.');
    if (source === 'hardware' && (meta.bytes !== 768000 || meta.packet_and_bulk_checksums !== 'verified')) throw new Error('Capture checksum evidence is incomplete.');
    if (source === 'demo' && meta.source !== 'demo') throw new Error('Demo capture is not labelled.');
    const pngFile = file.replace(/\.json$/, '.png');
    const stat = await fs.lstat(pngFile);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 33 || stat.size > 5 * 1024 * 1024) throw new Error('Unexpected capture image size.');
    const png = await fs.readFile(pngFile);
    if (!png.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) || png.toString('ascii', 12, 16) !== 'IHDR' || png.readUInt32BE(16) !== 800 || png.readUInt32BE(20) !== 480) throw new Error('Invalid capture image.');
    let annotation = { label: '', notes: '' };
    try {
      const data = await readJson(file.replace(/\.json$/, '.notes.json'), 16384);
      if (typeof data.label === 'string' && data.label.length <= 120 && typeof data.notes === 'string' && data.notes.length <= 8000) annotation = data;
    } catch { /* Missing or invalid annotations never invalidate original evidence. */ }
    const compactTime = /^scope-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})\.(\d{6})Z/.exec(name);
    const createdAt = compactTime ? `${compactTime[1]}-${compactTime[2]}-${compactTime[3]}T${compactTime[4]}:${compactTime[5]}:${compactTime[6]}.${compactTime[7].slice(0, 3)}Z` : meta.started_utc;
    if (!Number.isFinite(Date.parse(createdAt))) throw new Error('Capture date is invalid.');
    const id = `${saved ? source : 'preview'}:${name.replace(/\.json$/, '')}`;
    const capture = { id, createdAt, label: annotation.label, notes: annotation.notes, source, saved, imageUrl: `data:image/png;base64,${png.toString('base64')}`, width: 800, height: 480, checksumVerified: source === 'hardware' };
    this.registry.set(id, { pngFile, metaFile: file, capture });
    return capture;
  }
  async refreshLibrary() {
    for (const [id, record] of this.registry) if (record.capture.saved) this.registry.delete(id);
    const records = [];
    for (const source of ['hardware', 'demo']) {
      const directory = path.join(this.state.settings.storageDir, ...(source === 'demo' ? ['demo', 'captures'] : ['captures']));
      let files;
      try { files = await fs.readdir(directory); } catch (error) { if (error.code === 'ENOENT') continue; throw error; }
      const names = files.filter(name => (source === 'demo' ? DEMO_NAME : HARDWARE_NAME).test(name)).sort().reverse().slice(0, 100);
      for (const name of names) {
        try { records.push(await this.readCapture(path.join(directory, name), source, true)); } catch { /* Incomplete evidence remains on disk and is not presented as a capture. */ }
      }
    }
    this.state.captures = records.sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 100);
  }
  async listCaptures() {
    return this.exclusive(async () => { await this.refreshLibrary(); return structuredClone(this.state.captures); });
  }
  captureRecord(id) {
    if (typeof id !== 'string' || !this.registry.has(id)) throw new Error('Capture not found. Refresh the library and try again.');
    return this.registry.get(id);
  }
  async getCaptureFile(id) {
    return this.exclusive(async () => {
      const record = this.captureRecord(id);
      await this.readCapture(record.metaFile, record.capture.source, record.capture.saved);
      return record.pngFile;
    });
  }
  async updateCapture(input) {
    if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !['id', 'label', 'notes'].includes(key)) || typeof input.label !== 'string' || input.label.length > 120 || typeof input.notes !== 'string' || input.notes.length > 8000) throw new Error('Use a title up to 120 characters and notes up to 8000 characters.');
    return this.exclusive(async () => {
      const record = this.captureRecord(input.id);
      if (!record.capture.saved) throw new Error('Save a capture before adding notes.');
      await atomicJson(record.metaFile.replace(/\.json$/, '.notes.json'), { label: input.label, notes: input.notes });
      await this.refreshLibrary(); return structuredClone(this.captureRecord(input.id).capture);
    });
  }
  async prunePreviews(currentDirectory) {
    // This directory is app-owned scratch space, never the user's saved captures.
    const root = path.resolve(this.previewDir);
    const entries = await fs.readdir(root, { withFileTypes: true });
    const candidates = [];
    for (const entry of entries) {
      if (!entry.isDirectory() || !GUID_RE.test(entry.name)) continue;
      const target = path.resolve(root, entry.name);
      if (path.dirname(target) !== root || target === currentDirectory) continue;
      candidates.push({ target, mtime: (await fs.stat(target)).mtimeMs });
    }
    candidates.sort((a, b) => b.mtime - a.mtime);
    for (const { target } of candidates.slice(2)) {
      // Resolved absolute target is verified to be a direct, non-symlink child.
      for (const [id, entry] of this.registry) if (!entry.capture.saved && path.dirname(entry.metaFile) === target) this.registry.delete(id);
      await fs.rm(target, { recursive: true });
    }
  }
}
module.exports = { StudioService, validateSettingsPatch, friendlyError };
