#!/usr/bin/env node
/** One real Pi read round-trip. Never logs model text, tool payloads, or credentials. */
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export function summarize(events, marker, bridge = false) {
  const calls = new Map();
  const completed = new Set();
  const errors = new Set();
  let sawMarker = false;
  let final = '';
  let ended = false;
  let tokens = 0;
  let usageKnown = false;
  let reportedCost = 0;
  const errorKinds = new Set();
  for (const event of events) {
    if (!event || typeof event !== 'object' || Array.isArray(event)) {
      errors.add('invalid_event');
      continue;
    }
    if (event.type === 'tool_execution_start') {
      const id = event.toolCallId;
      if (typeof id !== 'string' || calls.has(id)) errors.add('invalid_or_duplicate_call');
      if (String(id).startsWith('cursor-replay-')) errors.add('replay_not_execution');
      if (bridge && !/^cursor-pi-bridge-(?:run-|call-)/.test(String(id))) errors.add('not_bridge_execution');
      if (event.toolName !== 'read') errors.add('unexpected_tool');
      calls.set(id, event.toolName);
    }
    if (event.type === 'tool_execution_end') {
      const id = event.toolCallId;
      if (!calls.has(id) || completed.has(id) || calls.get(id) !== event.toolName) errors.add('unmatched_result');
      completed.add(id);
      if (event.isError !== false) errors.add('tool_error');
      const content = event.result?.content;
      sawMarker ||= Array.isArray(content) && content.some(b => b.type === 'text' && String(b.text).includes(marker));
    }
    if (event.type === 'message_end' && event.message?.role === 'assistant') {
      const message = event.message;
      if (['error', 'aborted'].includes(message.stopReason)) errors.add('assistant_error');
      const detail = String(message.errorMessage || '');
      if (detail) {
        errorKinds.add(/invalid_grant|refresh token/i.test(detail) ? 'oauth_refresh' : /tool.*not found/i.test(detail) ? 'missing_tool' : /abort|cancel|pipeline/i.test(detail) ? 'abort' : /schema|validation|tool.call.id/i.test(detail) ? 'schema' : /timeout|network|connect|stalled/i.test(detail) ? 'network' : 'other');
      }
      final = Array.isArray(message.content) ? message.content.filter(b => b.type === 'text').map(b => b.text).join('') : '';
      const usage = message.usage;
      const values = ['input', 'output', 'cacheRead', 'cacheWrite'].map(k => usage?.[k]);
      if (values.every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0)) {
        usageKnown = true;
        tokens += values.reduce((a, b) => a + b, 0);
      }
      if (typeof usage?.cost?.total === 'number' && Number.isFinite(usage.cost.total)) reportedCost += usage.cost.total;
    }
    if (event.type === 'agent_end') ended = true;
  }
  if (calls.size !== 1 || completed.size !== 1) errors.add('expected_one_read');
  if (!sawMarker || !final.includes(marker)) errors.add('marker_not_verified');
  if (!ended) errors.add('agent_not_finished');
  return { status: errors.size ? 'failed' : 'passed', errors: [...errors].sort(), errorKinds: [...errorKinds].sort(),
    calls: calls.size, completed: completed.size, markerVerified: sawMarker && final.includes(marker),
    tokens: usageKnown ? tokens : null, reportedCostUsd: usageKnown ? reportedCost : null };
}

export function argumentsFor({ pi, extension, model, bridge, userExtensions = false }) {
  const prompt = bridge
    ? 'Call the exposed pi__read MCP tool exactly once with path="probe.txt". Do not use Cursor native tools. Then reply with exactly the file contents. No other actions.'
    : 'Use the read tool exactly once to read probe.txt, then reply with exactly the file contents. No other actions.';
  return [pi, '--offline', '--no-approve', ...(userExtensions ? [] : ['--no-extensions']), ...(extension ? ['-e', extension] : []),
    '--no-context-files', '--no-skills', '--no-prompt-templates', '--no-themes', '--no-session',
    '--tools', 'read', '--model', model, '--thinking', 'low', '--mode', 'json', '-p',
    '--system-prompt', 'Read only the requested fixture using the specified tool. Do not read other files or run commands.', prompt];
}

export async function probe(options) {
  const cwd = mkdtempSync(join(tmpdir(), 'pi-toolcall-probe-'));
  const marker = `PI_READ_${randomUUID()}`;
  writeFileSync(join(cwd, 'probe.txt'), marker + '\n', { mode: 0o600 });
  const events = [];
  let invalid = 0;
  let buffer = '';
  let bytes = 0;
  let stderrBytes = 0;
  let stderr = '';
  let extensionDigest = null;
  if (options.extension) {
    extensionDigest = createHash('sha256').update(readFileSync(join(options.extension, 'dist/index.js'))).digest('hex');
  }
  const [command, ...args] = argumentsFor(options);
  const env = { ...process.env, PI_CURSOR_SETTING_SOURCES: 'none', PI_CURSOR_EXPOSE_BUILTIN_TOOLS: options.bridge ? '1' : '0',
    PI_CURSOR_PI_TOOL_BRIDGE: '1', PI_CURSOR_SDK_EVENT_DEBUG: '0', PI_CURSOR_PI_TOOL_BRIDGE_DEBUG: '0',
    PI_TELEMETRY: '0', PI_SKIP_VERSION_CHECK: '1' };
  // No provider auth mutation/seeding. Explicitly selected provider uses existing credentials.
  delete env.PI_CURSOR_SDK_EVENT_DEBUG_STDERR;
  delete env.PI_CURSOR_LOCAL_FORCE;
  const started = Date.now();
  process.stderr.write('pi-toolcall-probe: starting isolated read fixture (no retry or process cancellation)\n');
  try {
    const child = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', chunk => {
      bytes += Buffer.byteLength(chunk);
      // Bound retained output, but keep draining. Do not kill an in-flight operation.
      if (bytes > 16 * 1024 * 1024) { buffer = ''; invalid++; return; }
      buffer += chunk;
      let index;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index); buffer = buffer.slice(index + 1);
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          if (['tool_execution_start', 'tool_execution_end', 'message_end', 'agent_end'].includes(event.type)) events.push(event);
        } catch { invalid++; }
      }
    });
    child.stderr.on('data', chunk => {
      stderrBytes += chunk.length;
      if (stderrBytes <= 32768) stderr += chunk.toString('utf8');
    });
    const code = await new Promise((res, rej) => { child.once('error', rej); child.once('close', res); });
    if (buffer.trim()) invalid++;
    const report = summarize(events, marker, options.bridge);
    if (code !== 0 || invalid) report.status = 'failed';
    return { schema: 'harness.pi-toolcall.v1', model: options.model, surface: options.bridge ? 'pi_bridge' : 'pi_native',
      extensionEntrySha256: extensionDigest, ...report, exitCode: code, invalidLines: invalid, stderrBytes,
      stderrClasses: Object.entries({ missing_module: /Cannot find (?:module|package)|MODULE_NOT_FOUND/, missing_export: /does not provide an export|No matching export/, load_failure: /Failed to load|Error loading/, type_error: /TypeError/, syntax_error: /SyntaxError/, reference_error: /ReferenceError/, missing_model: /[Mm]odel.*not found|[Nn]o models|[Uu]nknown (?:model|provider)/, missing_auth: /No API key|authentication|unauthorized/i, missing_file: /ENOENT/, permission: /EACCES|EPERM|[Pp]ermission denied/, missing_command: /command not found|node: not found/, peer_dependency: /peer dependenc/i }).filter(([, pattern]) => pattern.test(stderr)).map(([name]) => name),
      missingImports: [...stderr.matchAll(/Cannot find (?:module|package) ['"]([^'"]+)['"]/g)]
        .map(match => match[1]).filter(name => /^[.@a-zA-Z0-9_/-]{1,180}$/.test(name))
        .map(name => process.env.HOME && name.startsWith(process.env.HOME + '/') ? '<home>/' + name.slice(process.env.HOME.length + 1) : name),
      elapsedMs: Date.now() - started, userExtensions: options.userExtensions === true,
      scope: 'single-read-not-full-profile-or-release-gate' };
  } finally { rmSync(cwd, { recursive: true, force: true }); }
}

async function main(argv) {
  if (argv.includes('--help')) {
    process.stdout.write('Usage: toolcall-probe.mjs [--pi BIN] [--extension DIR] [--model PROVIDER/MODEL] [--bridge] [--user-extensions]\nUses existing provider credentials. No credential changes, retries, or session restarts.\n');
    return;
  }
  const options = { pi: 'pi', extension: null, model: 'cursor/grok-4.6:fast', bridge: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--bridge') { options.bridge = true; continue; }
    if (argv[i] === '--user-extensions') { options.userExtensions = true; continue; }
    const key = { '--pi': 'pi', '--extension': 'extension', '--model': 'model' }[argv[i]];
    if (!key || !argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error('invalid arguments');
    options[key] = argv[++i];
  }
  if (options.extension) options.extension = resolve(options.extension);
  const report = await probe(options);
  process.stdout.write(JSON.stringify(report) + '\n');
  process.exitCode = report.status === 'passed' ? 0 : 1;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(() => {
    process.stdout.write(JSON.stringify({ schema: 'harness.pi-toolcall.v1', status: 'blocked', reason: 'probe_setup_or_spawn_failed' }) + '\n');
    process.exitCode = 2;
  });
}
