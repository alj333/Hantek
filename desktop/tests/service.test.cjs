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
