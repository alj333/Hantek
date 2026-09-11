'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { test } = require('node:test');
const { parseBridgeOutput, runBridge } = require('../electron/bridge.cjs');

const COMMAND = { executable: 'C:\\Scope App\\scope-bridge.exe', args: ['fixed-script.py'] };
const REQUEST = { action: 'identify', guid: '5cb35641-beea-4a98-b06b-3cf4dca1911b' };
const RESULT = { vid: '049F', pid: '505A' };

function mockProcess() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.stdin = new EventEmitter();
  child.stdout.setEncoding = (encoding) => { child.stdout.encoding = encoding; };
  child.stderr.setEncoding = (encoding) => { child.stderr.encoding = encoding; };
  child.stdin.end = (input) => { child.input = input; };
  child.killCount = 0;
  child.kill = () => { child.killCount++; return true; };
  return child;
}

function startMock(request = REQUEST, options = {}) {
  const child = mockProcess();
  const spawns = [];
  const promise = runBridge(COMMAND, request, {
    timeoutMs: 1000,
    ...options,
    spawnProcess: (...args) => { spawns.push(args); return child; },
  });
  return { child, spawns, promise };
}

function sendResult(child, result = RESULT, code = 0) {
  child.stdout.emit('data', JSON.stringify({ ok: true, result }));
  child.emit('close', code);
}

test('successful response requires a structured result and a zero exit code', () => {
  assert.deepEqual(parseBridgeOutput(JSON.stringify({ ok: true, result: RESULT }), 0), RESULT);
  for (const output of [
    '', 'not json', '{}', 'null', '[]',
    JSON.stringify({ ok: 'true', result: RESULT }),
    JSON.stringify({ ok: true, result: null }),
    JSON.stringify({ ok: true, result: [] }),
    JSON.stringify({ ok: true, result: 'complete' }),
  ]) assert.throws(() => parseBridgeOutput(output, 0));
  assert.throws(() => parseBridgeOutput(JSON.stringify({ ok: true, result: RESULT }), 1));
  assert.throws(() => parseBridgeOutput(JSON.stringify({ ok: true, result: RESULT }), null));
});

test('failed responses retain uncertain execution evidence for diagnostics', () => {
  const evidence = { status: 'send_attempted_result_unknown', command: 'acquisition-stop', error: 'USB timeout' };
  assert.throws(
    () => parseBridgeOutput(JSON.stringify({ ok: false, error: 'USB timeout', result: evidence }), 1),
    (error) => {
      assert.equal(error.message, 'USB timeout');
      assert.deepEqual(error.result, evidence);
      return true;
    },
  );
  assert.throws(() => parseBridgeOutput(JSON.stringify({ ok: false, result: evidence }), 0), /unknown/i);
});

test('spawn keeps fixed arguments separate from bounded JSON input and opens no shell', async () => {
  const request = { action: 'screenshot', guid: REQUEST.guid, output_dir: 'C:\\Project & Tests\\captures' };
  const { child, spawns, promise } = startMock(request);
  assert.equal(spawns.length, 1);
  const [executable, args, options] = spawns[0];
  assert.equal(executable, COMMAND.executable);
  assert.deepEqual(args, COMMAND.args);
  assert.equal(options.shell, false);
  assert.equal(options.windowsHide, true);
  assert.deepEqual(options.stdio, ['pipe', 'pipe', 'pipe']);
  assert.equal(options.env.PYTHONUTF8, '1');
  assert.deepEqual(JSON.parse(child.input), request);
  assert.equal(child.stdout.encoding, 'utf8');
  assert.equal(child.stderr.encoding, 'utf8');
  sendResult(child);
  assert.deepEqual(await promise, RESULT);
  assert.equal(child.killCount, 0);
});

test('unsupported actions and oversized input fail before spawning', async () => {
  let spawns = 0;
  const spawnProcess = () => { spawns++; throw new Error('Must not spawn'); };
  for (const request of [
    { action: 'factory-reset' },
    { action: 'raw', command: 'anything' },
    { action: 'screenshot', output_dir: 'x'.repeat(17000) },
  ]) await assert.rejects(() => runBridge(COMMAND, request, { spawnProcess }));
  assert.equal(spawns, 0);
});

test('fragmented output is parsed only once the child exits successfully', async () => {
  const { child, promise } = startMock();
  const output = JSON.stringify({ ok: true, result: RESULT });
  let settled = false;
  promise.finally(() => { settled = true; });
  child.stdout.emit('data', output.slice(0, 12));
  child.stdout.emit('data', output.slice(12));
  await Promise.resolve();
  assert.equal(settled, false);
  child.emit('close', 0);
  assert.deepEqual(await promise, RESULT);
});

test('the deadline terminates the child, reports uncertainty and never retries', async () => {
  const { child, spawns, promise } = startMock({ action: 'acquisition-stop' }, { timeoutMs: 10 });
  await assert.rejects(promise, /timed out.*unknown/i);
  assert.equal(child.killCount, 1);
  assert.equal(spawns.length, 1);
  sendResult(child);
  assert.equal(spawns.length, 1);
});

for (const [stream, size] of [['stdout', 262145], ['stderr', 32769]]) {
  test(`${stream} overflow terminates the child and cannot become a successful response`, async () => {
    const { child, spawns, promise } = startMock();
    const rejection = assert.rejects(promise, /size limit/i);
    child[stream].emit('data', 'x'.repeat(size));
    await rejection;
    assert.equal(child.killCount, 1);
    sendResult(child);
    assert.equal(spawns.length, 1);
  });
}

test('an input pipe failure terminates the child instead of leaving an unbounded USB worker', async () => {
  const { child, spawns, promise } = startMock();
  const rejection = assert.rejects(promise, /closed its input/i);
  child.stdin.emit('error', new Error('write EPIPE'));
  await rejection;
  assert.equal(child.killCount, 1);
  assert.equal(spawns.length, 1);
});

test('failed child output preserves evidence and is not retried', async () => {
  const { child, spawns, promise } = startMock({ action: 'acquisition-stop' });
  const evidence = { status: 'send_attempted_result_unknown' };
  const rejection = assert.rejects(promise, (error) => {
    assert.match(error.message, /USB timeout/);
    assert.deepEqual(error.result, evidence);
    return true;
  });
  child.stdout.emit('data', JSON.stringify({ ok: false, error: 'USB timeout', result: evidence }));
  child.emit('close', 1);
  await rejection;
  assert.equal(spawns.length, 1);
});

test('startup failures are reported and do not cause another spawn', async () => {
  const { child, spawns, promise } = startMock();
  const rejection = assert.rejects(promise, /Could not start.*ENOENT/);
  child.emit('error', new Error('ENOENT'));
  await rejection;
  assert.equal(spawns.length, 1);
  await assert.rejects(() => runBridge(COMMAND, REQUEST, { spawnProcess: () => { throw new Error('spawn denied'); } }), /spawn denied/);
});

test('missing JSON reports bounded stderr while malformed JSON is never accepted', async () => {
  const first = startMock();
  const rejection = assert.rejects(first.promise, (error) => {
    assert.match(error.message, /^Scope runtime failed:/);
    assert.ok(error.message.length < 2100);
    return true;
  });
  first.child.stderr.emit('data', 'diagnostic '.repeat(300));
  first.child.emit('close', 1);
  await rejection;
  const second = startMock();
  const malformed = assert.rejects(second.promise, /invalid response/i);
  second.child.stdout.emit('data', '{truncated');
  second.child.emit('close', 0);
  await malformed;
});
