'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const { StudioService, validateSettingsPatch } = require('../electron/studio-service.cjs');

const GUID = '5cb35641-beea-4a98-b06b-3cf4dca1911b';
const OTHER_GUID = '0f8fad5b-d9cb-469f-a165-70867728950e';
const DEVICE = { model: 'DSO5102P', vid: '049F', pid: '505A', interface_number: 0 };
let fixtureSequence = 0;

function crc32(data) {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(kind, contents) {
  const type = Buffer.from(kind);
  const result = Buffer.alloc(contents.length + 12);
  result.writeUInt32BE(contents.length);
  type.copy(result, 4);
  contents.copy(result, 8);
  result.writeUInt32BE(crc32(Buffer.concat([type, contents])), contents.length + 8);
  return result;
}

function fixturePng(width = 800, height = 480) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 2;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', header),
    pngChunk('IDAT', zlib.deflateSync(Buffer.alloc(height * (width * 3 + 1)))),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

async function writeCapture(directory, overrides = {}, image = fixturePng()) {
  await fs.mkdir(directory, { recursive: true });
  const stamp = `20260911T160000.${String(++fixtureSequence).padStart(6, '0')}Z`;
  const id = `scope-${stamp}`;
  const base = path.join(directory, id);
  const metadata = {
    started_utc: stamp,
    device: DEVICE,
    instrument_settings_changed: false,
    request_hex: '5302002075',
    status: 'complete',
    width: 800,
    height: 480,
    bytes: 768000,
    frame_count: 192,
    sha256: 'a'.repeat(64),
    png_path: `${base}.png`,
    raw_path: `${base}.rgb565`,
    wire_path: `${base}.wire.bin`,
    packet_and_bulk_checksums: 'verified',
    ...overrides,
  };
  await fs.writeFile(`${base}.png`, image);
  await fs.writeFile(`${base}.json`, JSON.stringify(metadata));
  return { id, metadata, metadataPath: `${base}.json`, pngPath: `${base}.png` };
}

async function makeFixture(t, customBridge) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hantek-studio-test-'));
  t.after(async () => {
    // The directory comes directly from mkdtemp, and is checked before recursion.
    assert.ok(root.startsWith(path.join(os.tmpdir(), 'hantek-studio-test-')));
    await fs.rm(root, { recursive: true, force: true });
  });
  const calls = [];
  const bridge = async (request) => {
    calls.push(structuredClone(request));
    if (customBridge) return customBridge(request);
    if (request.action === 'identify') return { ...DEVICE };
    if (request.action === 'echo') return { echo: 'ok' };
    if (request.action === 'screenshot') return (await writeCapture(request.output_dir)).metadata;
    if (['acquisition-start', 'acquisition-stop'].includes(request.action)) {
      return { status: 'replies_received_usb_idle_execution_unverified', command: request.action };
    }
    if (request.action === 'panel-control') {
      return { status: 'sent_execution_unverified', control: request.control, count: request.count, instrument_state_verified: false };
    }
    if (request.action === 'read-settings') return { status: 'complete', raw_reply_hex: '00000000', interpretation_verified: false };
    throw new Error(`Unexpected bridge request: ${request.action}`);
  };
  const options = {
    storageDir: path.join(root, 'captures'),
    settingsPath: path.join(root, 'preferences', 'settings.json'),
    previewDir: path.join(root, 'preview'),
    bridge,
    version: '0.1.0',
  };
  const service = new StudioService(options);
  await service.initialize();
  return { root, calls, bridge, options, service };
}

async function hardwareConnect(service) {
  await service.updateSettings({ mode: 'hardware', interfaceGuid: GUID });
  await service.connect();
}

test('settings accept documented bounds and reject unsupported or malformed input', () => {
  for (const refreshIntervalMs of [3000, 60000]) {
    assert.doesNotThrow(() => validateSettingsPatch({ mode: 'demo', refreshIntervalMs, interfaceGuid: GUID }));
  }
  for (const input of [
    null, [], 'hardware', { mode: 'remote' }, { refreshIntervalMs: 2999 },
    { refreshIntervalMs: 60001 }, { refreshIntervalMs: 3000.5 },
    { refreshIntervalMs: '3000' }, { refreshIntervalMs: NaN },
    { interfaceGuid: 'not-a-guid' }, { interfaceGuid: '{00000000-0000-0000-0000-000000000000}' },
    { storageDir: '../other-project' }, { executable: 'arbitrary-program' },
    JSON.parse('{"__proto__":{"mode":"demo"}}'),
  ]) assert.throws(() => validateSettingsPatch(input), undefined, JSON.stringify(input));
});

test('initialization and disconnected operations do not access hardware', async (t) => {
  const { service, calls } = await makeFixture(t);
  assert.equal(service.getState().connected, false);
  await assert.rejects(() => service.capture());
  await assert.rejects(() => service.setAcquisition('start'));
  assert.equal(calls.length, 0);
});

test('demo use never invokes the bridge and never claims hardware checksum verification', async (t) => {
  const { service, calls } = await makeFixture(t, async () => { throw new Error('Demo touched hardware'); });
  await service.updateSettings({ mode: 'demo' });
  await service.connect();
  await service.checkConnection();
  const capture = await service.capture();
  assert.equal(capture.source, 'demo');
  assert.equal(capture.checksumVerified, false);
  assert.equal(capture.saved, true);
  const stopped = await service.setAcquisition('stop');
  if (stopped.capture) {
    assert.equal(stopped.capture.source, 'demo');
    assert.equal(stopped.capture.checksumVerified, false);
  }
  await service.setAcquisition('start');
  await service.disconnect();
  assert.equal(calls.length, 0);
});

test('connect refuses a mismatched device identity', async (t) => {
  const { service } = await makeFixture(t, async () => ({ ...DEVICE, pid: '0001' }));
  await service.updateSettings({ mode: 'hardware' });
  await assert.rejects(() => service.connect());
  assert.equal(service.getState().connected, false);
  assert.equal(service.getState().busy, false);
});

test('successful hardware captures retain verified evidence and known export paths', async (t) => {
  const { service, calls } = await makeFixture(t);
  await hardwareConnect(service);
  const capture = await service.capture();
  assert.equal(capture.source, 'hardware');
  assert.equal(capture.saved, true);
  assert.equal(capture.checksumVerified, true);
  assert.equal(capture.width, 800);
  assert.equal(capture.height, 480);
  assert.ok(capture.imageUrl);
  const knownPath = await service.getCaptureFile(capture.id);
  assert.equal(path.extname(knownPath), '.png');
  assert.deepEqual((await fs.readFile(knownPath)).subarray(0, 8), fixturePng().subarray(0, 8));
  assert.ok((await service.listCaptures()).some((entry) => entry.id === capture.id));
  const request = calls.find((entry) => entry.action === 'screenshot');
  assert.equal(request.guid.toLowerCase().replace(/[{}]/g, ''), GUID.replace(/[{}]/g, ''));
  assert.ok(path.isAbsolute(request.output_dir));
  if (request.log_dir !== undefined) assert.ok(path.isAbsolute(request.log_dir));
  assert.ok(calls.every((entry) => ['identify', 'echo', 'screenshot'].includes(entry.action)));
});

test('preview captures are not silently added to the saved capture library', async (t) => {
  const { service } = await makeFixture(t);
  await hardwareConnect(service);
  const before = await service.listCaptures();
  const capture = await service.capture({ save: false });
  assert.equal(capture.saved, false);
  assert.equal((await service.listCaptures()).length, before.length);
});

test('capture notes persist without altering the original transfer metadata', async (t) => {
  const { service, options } = await makeFixture(t);
  await hardwareConnect(service);
  const capture = await service.capture();
  const pngPath = await service.getCaptureFile(capture.id);
  const metadataPath = pngPath.replace(/\.png$/, '.json');
  const original = await fs.readFile(metadataPath, 'utf8');
  await service.updateCapture({ id: capture.id, label: 'Board A, cold start', notes: 'Operator observation only.' });
  assert.equal(await fs.readFile(metadataPath, 'utf8'), original);
  const reopened = new StudioService(options);
  await reopened.initialize();
  const saved = (await reopened.listCaptures()).find((entry) => entry.id === capture.id);
  assert.equal(saved.label, 'Board A, cold start');
  assert.equal(saved.notes, 'Operator observation only.');
  await assert.rejects(() => service.updateCapture({ id: capture.id, label: 'x'.repeat(100001), notes: '' }));
  await assert.rejects(() => service.updateCapture({ id: capture.id, label: '', notes: 'x'.repeat(100001) }));
});

test('capture lookup and annotation refuse traversal and arbitrary filesystem paths', async (t) => {
  const { service, root } = await makeFixture(t);
  for (const id of ['../settings', '..\\settings', path.join(root, 'secret.png'), 'scope-missing', '%2e%2e%2fsecret']) {
    await assert.rejects(async () => service.getCaptureFile(id));
    await assert.rejects(() => service.updateCapture({ id, label: 'wrong', notes: '' }));
  }
});

test('capture discovery excludes incomplete, unchecked, corrupt and wrong-size images', async (t) => {
  const { service, options } = await makeFixture(t);
  const captureDir = path.join(options.storageDir, 'captures');
  const valid = await writeCapture(captureDir);
  await writeCapture(captureDir, { status: 'incomplete' });
  await writeCapture(captureDir, { packet_and_bulk_checksums: 'failed' });
  await writeCapture(captureDir, {}, Buffer.from('This is not an image'));
  await writeCapture(captureDir, {}, fixturePng(64, 64));
  await fs.writeFile(path.join(captureDir, 'scope-20260911T161001.000001Z.json'), '{broken');
  const captures = await service.listCaptures();
  assert.equal(captures.length, 1);
  assert.equal(await service.getCaptureFile(captures[0].id), valid.pngPath);
});

test('conflicting failure evidence cannot be presented as a verified capture', async (t) => {
  const { service, options } = await makeFixture(t);
  await writeCapture(path.join(options.storageDir, 'captures'), {
    status: 'complete',
    error: 'Transfer interrupted before all evidence could be saved',
  });
  assert.equal((await service.listCaptures()).length, 0);
});

test('an export lookup rechecks a capture that changed after it was loaded', async (t) => {
  const { service } = await makeFixture(t);
  await hardwareConnect(service);
  const capture = await service.capture();
  const pngPath = await service.getCaptureFile(capture.id);
  await fs.writeFile(pngPath, 'Replaced with a non-image file');
  await assert.rejects(() => service.getCaptureFile(capture.id));
});

test('the bridge cannot redirect a capture to a file outside its chosen output directory', async (t) => {
  let outside;
  const { service, root } = await makeFixture(t, async (request) => {
    if (request.action === 'identify') return DEVICE;
    if (request.action === 'echo') return { echo: 'ok' };
    if (request.action === 'screenshot') return (await writeCapture(outside)).metadata;
    throw new Error('Unexpected command');
  });
  outside = path.join(root, 'outside');
  await hardwareConnect(service);
  await assert.rejects(() => service.capture());
  assert.equal((await service.listCaptures()).length, 0);
});

test('busy hardware operations reject competing mutations and release the lock after failure', async (t) => {
  let enter;
  const entered = new Promise((resolve) => { enter = resolve; });
  let release;
  const blocked = new Promise((resolve, reject) => { release = reject; });
  const { service, calls, root } = await makeFixture(t, async () => {
    enter();
    await blocked;
  });
  await service.updateSettings({ mode: 'hardware' });
  const connecting = service.connect();
  const connectionFailure = assert.rejects(connecting, /USB unavailable/);
  await entered;
  assert.equal(service.getState().busy, true);
  await assert.rejects(() => service.connect());
  await assert.rejects(() => service.capture());
  await assert.rejects(() => service.disconnect());
  await assert.rejects(() => service.updateSettings({ mode: 'demo' }));
  await assert.rejects(() => service.setStorageDirectory(path.join(root, 'other')));
  assert.equal(calls.length, 1);
  release(new Error('USB unavailable'));
  await connectionFailure;
  assert.equal(service.getState().busy, false);
  assert.equal(service.getState().connected, false);
  assert.ok(service.getState().activity.some((entry) => entry.kind === 'error'));
});

test('an acquisition failure is reported without retrying or taking a misleading screenshot', async (t) => {
  const { service, calls } = await makeFixture(t, async (request) => {
    if (request.action === 'identify') return DEVICE;
    if (request.action === 'echo') return { echo: 'ok' };
    throw new Error('Send attempted; result unknown');
  });
  await hardwareConnect(service);
  await assert.rejects(() => service.setAcquisition('stop'), /result unknown/i);
  assert.equal(calls.filter((entry) => entry.action === 'acquisition-stop').length, 1);
  assert.equal(calls.filter((entry) => entry.action === 'screenshot').length, 0);
  assert.equal(service.getState().busy, false);
  assert.ok(service.getState().activity.some((entry) => entry.kind === 'error'));
});

test('a sent acquisition request with failed visual verification stays explicitly unverified', async (t) => {
  const { service, calls } = await makeFixture(t, async (request) => {
    if (request.action === 'identify') return DEVICE;
    if (request.action === 'echo') return { echo: 'ok' };
    if (request.action === 'acquisition-stop') {
      return { status: 'replies_received_usb_idle_execution_unverified', command: request.action };
    }
    throw new Error('Screenshot transfer interrupted');
  });
  await hardwareConnect(service);
  const result = await service.setAcquisition('stop');
  assert.equal(result.capture, null);
  assert.match(result.message, /unverified/i);
  assert.match(result.message, /screen.*(fail|interrupt)/i);
  assert.equal(calls.filter((entry) => entry.action === 'acquisition-stop').length, 1);
  assert.equal(calls.filter((entry) => entry.action === 'screenshot').length, 1);
  assert.equal((await service.listCaptures()).length, 0);
});

test('invalid acquisition requests are rejected before any hardware command', async (t) => {
  const { service, calls } = await makeFixture(t);
  await hardwareConnect(service);
  const before = calls.length;
  for (const command of ['reset', 'STOP', '', null, { state: 'start' }]) {
    await assert.rejects(() => service.setAcquisition(command));
  }
  assert.equal(calls.length, before);
});

test('switching device configuration disconnects and persists without accessing hardware', async (t) => {
  const { service, calls, options } = await makeFixture(t);
  await hardwareConnect(service);
  const before = calls.length;
  await service.updateSettings({ mode: 'demo', interfaceGuid: OTHER_GUID, refreshIntervalMs: 60000 });
  assert.equal(service.getState().connected, false);
  assert.equal(calls.length, before);
  const reopened = new StudioService(options);
  await reopened.initialize();
  const state = reopened.getState();
  assert.equal(state.settings.mode, 'demo');
  assert.equal(state.settings.refreshIntervalMs, 60000);
  assert.equal(state.settings.interfaceGuid.toLowerCase().replace(/[{}]/g, ''), OTHER_GUID.replace(/[{}]/g, ''));
  assert.equal(state.connected, false);
});

test('returned application state cannot be mutated to authorize hardware access', async (t) => {
  const { service, calls } = await makeFixture(t);
  const state = service.getState();
  state.connected = true;
  state.settings.mode = 'demo';
  state.activity.push({ kind: 'success', message: 'injected' });
  assert.equal(service.getState().connected, false);
  assert.ok(service.getState().activity.every((entry) => entry.message !== 'injected'));
  await assert.rejects(() => service.capture());
  assert.equal(calls.length, 0);
});

function representativeControls(service) {
  const catalog = service.getState().controlCatalog;
  assert.ok(Array.isArray(catalog) && catalog.length > 0);
  const button = catalog.find(control => control.kind === 'button');
  const rotary = catalog.find(control => control.kind === 'rotary');
  assert.ok(button, 'A front-panel button must be available');
  assert.ok(rotary, 'A front-panel rotary control must be available');
  return { catalog, button, rotary };
}

test('panel controls expose provenance but no generic command or payload entry point', async (t) => {
  const { service } = await makeFixture(t);
  const { catalog } = representativeControls(service);
  assert.equal(new Set(catalog.map(control => control.id)).size, catalog.length);
  for (const control of catalog) {
    assert.ok(['bench-pending', 'screen-verified'].includes(control.validation));
    assert.ok(typeof control.label === 'string' && control.label.length > 0);
    assert.equal(control.maxCount, control.kind === 'rotary' ? 5 : 1);
    for (const field of ['payload', 'payload_hex', 'command', 'command_hex', 'key_code', 'keycode']) assert.equal(field in control, false);
  }
  const original = service.getState().controlCatalog;
  catalog[0].validation = 'invented';
  assert.deepEqual(service.getState().controlCatalog, original);
});

test('invalid panel requests are rejected before the bridge sees any command', async (t) => {
  const { service, calls } = await makeFixture(t);
  const { button, rotary } = representativeControls(service);
  await hardwareConnect(service);
  const countBefore = calls.length;
  for (const request of [
    null, [], 'start', {}, { control: 'factory-reset' }, { control: '../arbitrary' },
    { control: button.id, count: 2 }, { control: rotary.id, count: 0 },
    { control: rotary.id, count: 6 }, { control: rotary.id, count: 1.5 },
    { control: rotary.id, count: '1' }, { control: rotary.id, count: NaN },
    { control: rotary.id, count: Infinity }, { control: rotary.id, count: null },
    { control: button.id, payload: '00' }, { control: button.id, log_dir: '../elsewhere' },
  ]) await assert.rejects(() => service.panelAction(request));
  assert.equal(calls.length, countBefore);
});

test('panel actions and settings reads require an explicit connection', async (t) => {
  const { service, calls } = await makeFixture(t);
  const { button } = representativeControls(service);
  await assert.rejects(() => service.panelAction({ control: button.id }));
  await assert.rejects(() => service.readSettings());
  assert.equal(calls.length, 0);
});

test('named button and bounded rotary requests use one command each and leave execution unverified', async (t) => {
  const { service, calls } = await makeFixture(t);
  const { catalog, button, rotary } = representativeControls(service);
  await hardwareConnect(service);
  for (const input of [{ control: button.id }, { control: rotary.id, count: 5 }]) {
    const result = await service.panelAction(input);
    assert.ok(result.capture);
    assert.equal(result.capture.source, 'hardware');
    assert.equal(result.capture.saved, false);
    assert.match(result.message, /requested/i);
    assert.match(result.message, /check.*screen|screen.*confirm/i);
  }
  const actions = calls.filter(request => request.action === 'panel-control');
  assert.equal(actions.length, 2);
  assert.deepEqual(actions.map(({ control, count }) => ({ control, count })), [
    { control: button.id, count: 1 }, { control: rotary.id, count: 5 },
  ]);
  for (const request of actions) {
    assert.ok(path.isAbsolute(request.log_dir));
    assert.deepEqual(Object.keys(request).sort(), ['action', 'control', 'count', 'guid', 'log_dir']);
  }
  assert.equal(calls.filter(request => request.action === 'screenshot').length, 2);
  assert.deepEqual(service.getState().controlCatalog, catalog);
  assert.equal((await service.listCaptures()).length, 0);
});

test('demo panel actions and settings are simulated, logged, and never touch the bridge', async (t) => {
  const { service, calls, options } = await makeFixture(t, async () => { throw new Error('Demo accessed hardware'); });
  const { catalog, button, rotary } = representativeControls(service);
  await service.updateSettings({ mode: 'demo' });
  await service.connect();
  for (const input of [{ control: button.id }, { control: rotary.id, count: 5 }]) {
    const result = await service.panelAction(input);
    assert.match(result.message, /demo.*simulated/i);
    assert.equal(result.capture.source, 'demo');
    assert.equal(result.capture.checksumVerified, false);
    assert.equal(result.capture.saved, false);
  }
  const settings = await service.readSettings();
  assert.equal(settings.record.source, 'demo');
  assert.equal(settings.record.hardware_access, false);
  assert.equal(settings.record.instrument_state_verified, false);
  const logDir = path.join(options.storageDir, 'demo', 'logs');
  const files = (await fs.readdir(logDir)).filter(name => /^panel-.*\.json$/.test(name));
  assert.equal(files.length, 2);
  for (const name of files) {
    const record = JSON.parse(await fs.readFile(path.join(logDir, name), 'utf8'));
    assert.equal(record.source, 'demo');
    assert.equal(record.hardware_access, false);
    assert.equal(record.instrument_state_verified, false);
  }
  const settingsFiles = (await fs.readdir(logDir)).filter(name => /^settings-.*\.json$/.test(name));
  assert.equal(settingsFiles.length, 1, 'The Save settings record action must persist its demo record');
  const savedSettings = JSON.parse(await fs.readFile(path.join(logDir, settingsFiles[0]), 'utf8'));
  assert.equal(savedSettings.source, 'demo');
  assert.equal(savedSettings.hardware_access, false);
  assert.equal(savedSettings.instrument_state_verified, false);
  assert.equal(calls.length, 0);
  assert.deepEqual(service.getState().controlCatalog, catalog);
});

test('a failed panel send disconnects and is never repeated or followed by a misleading preview', async (t) => {
  const { service, calls } = await makeFixture(t, async request => {
    if (request.action === 'identify') return DEVICE;
    throw new Error('Panel send attempted; result unknown');
  });
  const { button } = representativeControls(service);
  await hardwareConnect(service);
  await assert.rejects(() => service.panelAction({ control: button.id }), /result unknown/i);
  assert.equal(calls.filter(request => request.action === 'panel-control').length, 1);
  assert.equal(calls.filter(request => request.action === 'screenshot').length, 0);
  assert.equal(service.getState().connected, false);
  assert.equal(service.getState().busy, false);
});

test('a sent panel action with a failed preview remains distinct from a verified result', async (t) => {
  const { service, calls } = await makeFixture(t, async request => {
    if (request.action === 'identify') return DEVICE;
    if (request.action === 'panel-control') return { status: 'sent_execution_unverified', instrument_state_verified: false };
    throw new Error('Screenshot transfer interrupted');
  });
  const { button } = representativeControls(service);
  await hardwareConnect(service);
  const result = await service.panelAction({ control: button.id });
  assert.equal(result.capture, null);
  assert.match(result.message, /requested.*screen.*failed/i);
  assert.match(result.message, /unverified/i);
  assert.equal(calls.filter(request => request.action === 'panel-control').length, 1);
  assert.equal(calls.filter(request => request.action === 'screenshot').length, 1);
  assert.equal(service.getState().connected, false);
  assert.equal(service.getState().busy, false);
});

test('an in-flight panel command rejects all competing hardware mutations and reads', async (t) => {
  let release, enter;
  const entered = new Promise(resolve => { enter = resolve; });
  const waiting = new Promise(resolve => { release = resolve; });
  const { service, calls } = await makeFixture(t, async request => {
    if (request.action === 'identify') return DEVICE;
    if (request.action === 'panel-control') { enter(); await waiting; return { status: 'sent_execution_unverified' }; }
    if (request.action === 'screenshot') return (await writeCapture(request.output_dir)).metadata;
    throw new Error('Unexpected competing command');
  });
  const { button } = representativeControls(service);
  await hardwareConnect(service);
  const pending = service.panelAction({ control: button.id });
  await entered;
  await assert.rejects(() => service.panelAction({ control: button.id }));
  await assert.rejects(() => service.setAcquisition('stop'));
  await assert.rejects(() => service.capture());
  await assert.rejects(() => service.readSettings());
  await assert.rejects(() => service.disconnect());
  assert.equal(calls.filter(request => request.action === 'panel-control').length, 1);
  release();
  assert.ok((await pending).capture);
  assert.equal(service.getState().busy, false);
});

test('hardware settings replies are presented as raw records with interpretation pending', async (t) => {
  const { service, calls } = await makeFixture(t);
  await hardwareConnect(service);
  const result = await service.readSettings();
  assert.match(result.message, /raw.*numeric interpretation.*validation/i);
  assert.equal(result.record.interpretation_verified, false);
  const requests = calls.filter(request => request.action === 'read-settings');
  assert.equal(requests.length, 1);
  assert.ok(path.isAbsolute(requests[0].log_dir));
  assert.equal(calls.filter(request => request.action === 'screenshot').length, 0);
});
