const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

function runtimeCommand({ packaged, resourcesPath, repoRoot }) {
  if (packaged) {
    const executable = path.join(resourcesPath, 'scope-bridge', 'scope-bridge.exe');
    if (!fs.existsSync(executable)) throw new Error('The bundled scope runtime is missing. Rebuild or restore the complete application.');
    return { executable, args: [] };
  }
  const explicit = process.env.HANTEK_PYTHON;
  const candidates = explicit ? [explicit] : [
    path.join(repoRoot, '.local', 'build-venv', 'Scripts', 'python.exe'),
    path.join(process.env.USERPROFILE || '', '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe'),
    ...(process.env.PATH || '').split(path.delimiter).map(folder => path.join(folder, 'python.exe')),
  ];
  const executable = candidates.find(file => path.isAbsolute(file) && !/[\\/]WindowsApps[\\/]/i.test(file) && fs.existsSync(file));
  if (!executable) throw new Error('Python was not found for development. Set HANTEK_PYTHON or build the standalone app.');
  return { executable, args: [path.join(repoRoot, 'src', 'desktop_bridge.py')] };
}
function parseBridgeOutput(output, code) {
  let value;
  try { value = JSON.parse(output); } catch { throw new Error('The scope runtime returned an invalid response. Instrument state may be unknown.'); }
  if (!value || typeof value !== 'object' || typeof value.ok !== 'boolean') throw new Error('Invalid scope response envelope.');
  if (code !== 0 || !value.ok) {
    const error = new Error(typeof value.error === 'string' ? value.error : 'The scope request failed. Its result may be unknown.');
    if (value.result && typeof value.result === 'object') error.result = value.result;
    throw error;
  }
  if (!value.result || typeof value.result !== 'object' || Array.isArray(value.result)) throw new Error('The scope runtime returned no result.');
  return value.result;
}
function runBridge(command, request, { timeoutMs = 45000, spawnProcess = spawn } = {}) {
  if (!['identify', 'echo', 'screenshot', 'acquisition-start', 'acquisition-stop', 'controls', 'panel-control', 'read-settings'].includes(request.action)) return Promise.reject(new Error('Unsupported scope action.'));
  const input = JSON.stringify(request);
  if (Buffer.byteLength(input) > 16384) return Promise.reject(new Error('Scope request is too large.'));
  return new Promise((resolve, reject) => {
    let stdout = '', stderr = '', settled = false;
    const child = spawnProcess(command.executable, command.args, { shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONUTF8: '1' } });
    const finish = (error, result) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(result);
    };
    const timer = setTimeout(() => {
      child.kill(); finish(new Error('Scope request timed out. The result may be unknown; check the screen before retrying.'));
    }, timeoutMs);
    child.on('error', error => finish(new Error(`Could not start the scope runtime: ${error.message}`)));
    child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data', data => { if (settled) return; stdout += data; if (stdout.length > 262144) { child.kill(); finish(new Error('Scope response exceeded its size limit.')); } });
    child.stderr.on('data', data => { if (settled) return; stderr += data; if (stderr.length > 32768) { child.kill(); finish(new Error('Scope error output exceeded its size limit.')); } });
    child.stdin.on('error', error => { child.kill(); finish(new Error(`The scope runtime closed its input: ${error.message}`)); });
    child.on('close', code => {
      if (settled) return;
      try { finish(null, parseBridgeOutput(stdout, code)); }
      catch (error) { if (!stdout.trim() && stderr.trim()) error.message = `Scope runtime failed: ${stderr.trim().slice(0, 2000)}`; finish(error); }
    });
    child.stdin.end(input);
  });
}
module.exports = { runtimeCommand, runBridge, parseBridgeOutput };
