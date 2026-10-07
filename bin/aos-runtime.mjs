#!/usr/bin/env node
// Public, display-only projections. Never send telemetry into model context.
import { createHash, randomUUID } from 'node:crypto';
import { readFile, writeFile, mkdir, rename, lstat, copyFile } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { homedir, hostname } from 'node:os';
import { resolve, join, dirname } from 'node:path';
import { spawn } from 'node:child_process';
import { pathToFileURL, fileURLToPath } from 'node:url';

const LIMIT = 4 * 1024 * 1024;
const phases = new Set(['preparing', 'prepared', 'aligning', 'aligned', 'queued', 'switched', 'successor', 'compacted-triage', 'failed']);
const hash = data => createHash('sha256').update(data).digest('hex');
const number = value => Number.isSafeInteger(value) && value >= 0;
const id = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$/.test(value);
const text = value => typeof value === 'string' && value.length > 0 && value.length <= 1024;
const fail = code => { throw new Error(code); };
const safe = path => typeof path === 'string' && path.length > 0 && !/(^|[/\\])(?:auth(?:\.json)?|\.env[^/\\]*|credentials[^/\\]*|[^/\\]*\.(?:pem|key)|id_(?:rsa|ed25519))($|[/\\])/i.test(path);
export function publicText(value) {
  return typeof value === 'string' && /^[A-Za-z0-9 ._:@/+-]{1,160}$/.test(value) ? value : 'redacted';
}
function exact(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !keys.includes(key))) fail('schema_rejected');
}
async function json(path) {
  if (!safe(path)) fail('protected_path');
  const stat = await lstat(path);
  if (!stat.isFile() || stat.size > LIMIT) fail('invalid_file');
  return JSON.parse(await readFile(path, 'utf8'));
}
async function atomic(path, value) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const tmp = `${path}.${randomUUID()}.tmp`;
  await writeFile(tmp, JSON.stringify(value) + '\n', { mode: 0o600, flag: 'wx' });
  await rename(tmp, path);
}
export async function command(argv, input, timeout = 15000) {
  if (!Array.isArray(argv) || !argv.length || argv.some(arg => typeof arg !== 'string' || arg.includes('\0'))) fail('invalid_command');
  return new Promise((done, reject) => {
    // Adapter stderr is untrusted and may contain auth material; never relay it.
    const child = spawn(argv[0], argv.slice(1), { stdio: ['pipe', 'pipe', 'ignore'], shell: false });
    let out = ''; let oversized = false;
    const timer = setTimeout(() => { reject(new Error('adapter_timeout')); child.stdin.destroy(); child.stdout.destroy(); child.unref(); }, timeout);
    child.on('error', () => { clearTimeout(timer); reject(new Error('adapter_unavailable')); });
    child.stdin.on('error', () => {});
    child.stdout.on('data', chunk => { if (out.length + chunk.length > LIMIT) oversized = true; else out += chunk; });
    child.on('close', code => {
      clearTimeout(timer);
      if (oversized || code !== 0) return reject(new Error(oversized ? 'adapter_output_limit' : 'adapter_failed'));
      try { done(JSON.parse(out)); } catch { reject(new Error('adapter_invalid_json')); }
    });
    child.stdin.end(JSON.stringify(input) + '\n');
  });
}
export function identity(value) {
  exact(value, ['schema', 'session_id', 'harness', 'host', 'profile', 'profile_digest', 'worktree', 'project', 'session_file']);
  if (value.schema !== 'aos.identity.v1' || !['pi', 'hermes', 'claude', 'cursor', 'codex', 'devin'].includes(value.harness)
      || !['session_id', 'host', 'profile', 'project'].every(key => id(value[key]))
      || !/^[a-f0-9]{64}$/.test(value.profile_digest) || !text(value.worktree)
      || (value.session_file !== undefined && !safe(value.session_file))) fail('identity_rejected');
  return value;
}
export function projectBinding(reply, who, kernel, operation, now = Date.now()) {
  // A saved registration record is not authoritative acceptance. Both receipt
  // and independent observation must correlate exact native identity and scope.
  const binding = reply?.binding;
  if (reply?.schema !== 'aos.kernel-binding.v1' || reply.kernel_id !== kernel || !binding
      || !['session_id', 'harness', 'host', 'profile', 'profile_digest', 'worktree', 'project'].every(key => binding[key] === who[key])
      || binding.operation_id !== operation || binding.accepted !== true) fail('binding_readback_rejected');
  const stamp = Date.parse(reply.observed_at);
  const beat = Date.parse(reply.heartbeat_at);
  const fresh = Number.isFinite(stamp) && Number.isFinite(beat) && stamp <= now && beat <= now && now - stamp <= 30000 && now - beat <= 30000;
  const nodes = Array.isArray(reply.graph?.nodes) ? reply.graph.nodes : [];
  const edges = Array.isArray(reply.graph?.edges) ? reply.graph.edges : [];
  const scoped = reply.graph?.session_id === who.session_id && reply.graph?.project === who.project && reply.graph?.kernel_id === kernel;
  const graph = scoped && fresh ? {
    nodes: nodes.slice(0, 200).filter(node => id(node?.id)).map(node => ({ id: node.id, label: publicText(node.label ?? node.id), state: ['running', 'succeeded', 'failed', 'blocked', 'stale'].includes(node.state) ? node.state : 'unknown' })),
    edges: edges.slice(0, 400).filter(edge => id(edge?.src) && id(edge?.dst)).map(edge => ({ src: edge.src, dst: edge.dst, rel: publicText(edge.rel) })),
  } : { nodes: [], edges: [] };
  return { kernel: { id: kernel, state: fresh ? 'attached' : 'stale', observed_at: reply.observed_at, heartbeat_at: reply.heartbeat_at, operation_id: operation }, graph: { state: fresh && scoped ? 'live' : 'unavailable', ...graph } };
}
export async function bind(who, adapter, kernel, run = command) {
  identity(who);
  if (!Array.isArray(adapter) || !adapter.length || adapter.length > 16 || adapter.some(arg => typeof arg !== 'string' || arg.length > 1024 || /[\r\n\0]/.test(arg) || /(?:^--?(?:token|api-key|password|secret|authorization|header)(?:=|$)|^(?:Bearer|Basic) |(?:access_token|api_key|password)=|^sk-[A-Za-z0-9])/i.test(arg))) fail('public_adapter_required');
  if (!id(kernel)) fail('kernel_pin_required');
  const operation = hash(JSON.stringify(Object.fromEntries(['session_id', 'harness', 'host', 'profile', 'profile_digest', 'worktree', 'project'].map(key => [key, who[key]]))));
  const request = { schema: 'aos.kernel-binding.v1', kernel_id: kernel, operation_id: operation, identity: who };
  const receipt = await run(adapter, { ...request, op: 'bind' });
  if (receipt?.schema !== request.schema || receipt.kernel_id !== kernel || receipt.operation_id !== operation || receipt.accepted !== true) fail('binding_receipt_rejected');
  const observed = await run(adapter, { ...request, op: 'observe' });
  const projection = projectBinding(observed, who, kernel, operation);
  if (projection.kernel.state !== 'attached' || projection.graph.state !== 'live') fail('binding_not_live');
  return { ...projection, operation_id: operation };
}
export async function usage(path, sid) {
  if (!safe(path) || !path.endsWith('.jsonl') || !(await lstat(path)).isFile()) fail('protected_usage_path');
  const totals = { input: 0, output: 0, cache_read: null, cache_write: null, total: null, turns: 0 };
  let latest; let native; const persisted = new Map(); const streamed = new Map();
  const reported = { cache_read: 0, cache_write: 0, total: 0 };
  const lines = createInterface({ input: createReadStream(path), crlfDelay: Infinity });
  for await (const line of lines) {
    let row; try { row = JSON.parse(line); } catch { continue; }
    if (row.type === 'session') { native = row.id; if (native && native !== sid) fail('session_mismatch'); continue; }
    if (!['message', 'message_end'].includes(row.type) || row.message?.role !== 'assistant') continue;
    const msg = row.message; const data = msg.usage;
    if (!data || !number(data.input) || !number(data.output)) continue;
    // Persistence is authoritative if present. Stream logs are a separate source;
    // no mixing two formats or replaying duplicate message IDs into the ledger.
    const key = msg.id ?? row.id ?? hash(JSON.stringify([msg.timestamp, data]));
    (row.type === 'message' ? persisted : streamed).set(key, data);
  }
  if (native && native !== sid) fail('session_mismatch');
  const rows = persisted.size ? persisted.values() : streamed.values();
  for (const data of rows) {
    totals.turns++;
    totals.input += data.input; totals.output += data.output;
    for (const [out, field] of [['cache_read', 'cacheRead'], ['cache_write', 'cacheWrite'], ['total', 'totalTokens']]) {
      if (number(data[field])) { totals[out] = (totals[out] ?? 0) + data[field]; reported[out]++; }
    }
    latest = data;
  }
  for (const key of Object.keys(reported)) if (reported[key] !== totals.turns) totals[key] = null;
  return { tokens: totals.turns ? totals : null, context: number(latest?.context_used) && number(latest?.context_max) && latest.context_max > 0
    ? { used: latest.context_used, limit: latest.context_max, percent: 100 * latest.context_used / latest.context_max, state: 'reported' }
    : { state: 'unavailable' } };
}
export function handoff(value, sid) {
  if (value?.schema !== 'pi.handoff-prep.v1' || value.source_session_id !== sid || !phases.has(value.phase)) return { phase: 'unavailable' };
  return { phase: value.phase, successor: id(value.child_session_id) ? value.child_session_id : null, thresholds: [60, 70, 75] };
}
async function emit(event) {
  // Zero/many file sinks, JSON only; reject non-file sinks rather than guessing
  // credentials or mixing events into stdout. Payload contains no source bytes.
  const sinks = (process.env.CARTESIA_EVENT_SINKS ?? '').split(',').filter(Boolean);
  for (const sink of sinks) {
    if (!sink.startsWith('file:')) fail('event_sink_unsupported');
    const path = sink.slice(5);
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    await writeFile(path, JSON.stringify(event) + '\n', { flag: 'a', mode: 0o600 });
  }
}
export function telemetry(value, sid, now = Date.now()) {
  const at = Date.parse(value?.observed_at);
  if (value?.schema !== 'aos.session-telemetry.v1' || value.session_id !== sid || !Number.isFinite(at) || at > now || now - at > 30000) return null;
  const data = value.tokens;
  const context = value.context;
  return {
    tokens: number(data?.input) && number(data?.output) && number(data?.turns) ? { input: data.input, output: data.output, turns: data.turns,
      cache_read: number(data.cache_read) ? data.cache_read : null, cache_write: number(data.cache_write) ? data.cache_write : null, total: number(data.total) ? data.total : null } : null,
    context: number(context?.used) && number(context?.limit) && context.limit > 0 ? { used: context.used, limit: context.limit, percent: 100 * context.used / context.limit, state: 'reported' } : { state: 'unavailable' },
  };
}
export async function status(sid, cfg, path, home = homedir()) {
  if (!id(sid) || sid.includes('/')) fail('session_id_rejected');
  let snapshot = { tokens: null, context: { state: 'unavailable' } };
  if (path) { try { snapshot = await usage(path, sid); } catch { snapshot.error = 'usage_unavailable'; } }
  let prep;
  try { prep = await json(join(home, '.pi/agent/handoffs', `${sid}.json`)); } catch {}
  let projected = { kernel: { state: 'unbound' }, graph: { state: 'unavailable', nodes: [], edges: [] } };
  if (cfg) {
    try {
      identity(cfg.identity);
      if (cfg.identity.session_id !== sid) fail('session_mismatch');
      const reply = await command(cfg.adapter, { schema: 'aos.kernel-binding.v1', op: 'observe', kernel_id: cfg.kernel_id, operation_id: cfg.operation_id, identity: cfg.identity });
      projected = projectBinding(reply, cfg.identity, cfg.kernel_id, cfg.operation_id);
      if (projected.kernel.state === 'attached') {
        const observed = telemetry(reply.telemetry, sid);
        if (observed) snapshot = { tokens: observed.tokens ?? snapshot.tokens, context: observed.context.state === 'reported' ? observed.context : snapshot.context };
      }
      if (projected.kernel.state === 'attached' && reply.handoff?.schema === 'aos.handoff.v1' && reply.handoff.source_session_id === sid) {
        prep = { ...reply.handoff, schema: 'pi.handoff-prep.v1' };
      }
    } catch { projected.kernel = { state: 'disconnected' }; }
  }
  return { schema: 'aos.session.v1', session_id: sid, captured_at: new Date().toISOString(), ...snapshot, handoff: handoff(prep, sid), ...projected };
}
function artifact(value) {
  exact(value, ['name', 'source', 'destination', 'expected']);
  if (!id(value.name) || !safe(value.source) || !safe(value.destination) || (value.expected !== undefined && value.expected !== null && !/^[a-f0-9]{64}$/.test(value.expected))) fail('artifact_rejected');
  return value;
}
export async function target(request, root, run = command) {
  exact(request, ['schema', 'op', 'artifacts']);
  if (request.schema === 'aos.fleet-target.v1' && request.op === 'discover' && request.artifacts === undefined) {
    let sandboxes = { state: 'blocked', items: [] };
    try {
      const rows = await run(['podman', 'ps', '-a', '--format', 'json'], {});
      if (!Array.isArray(rows)) fail('sandbox_inventory_rejected');
      const items = rows.map(row => {
        const name = Array.isArray(row.Names) ? row.Names[0] : row.Names;
        if (!id(name) || name.includes('/')) fail('sandbox_identity_rejected');
        return { name, state: ['running', 'exited', 'created', 'paused', 'stopped'].includes(row.State) ? row.State : 'unknown' };
      });
      sandboxes = { state: 'observed', items };
    } catch {}
    return { schema: request.schema, host: publicText(hostname()), toolkit_digest: hash(await readFile(fileURLToPath(import.meta.url))), sandboxes };
  }
  if (request.schema !== 'aos.fleet-target.v1' || !['check', 'apply'].includes(request.op) || !Array.isArray(request.artifacts)) fail('target_request_rejected');
  const items = [];
  for (const row of request.artifacts) {
    exact(row, ['name', 'destination', 'digest', 'content', 'expected']);
    if (!id(row.name) || !safe(row.destination) || !/^[a-f0-9]{64}$/.test(row.digest)) fail('target_artifact_rejected');
    const path = resolve(root, row.destination);
    if (!path.startsWith(resolve(root) + '/') || row.destination.startsWith('/')) fail('destination_outside_root');
    // Refuse symlink components, including the target. Never follow links to
    // another profile/home or overwrite files outside the approved root.
    let cursor = path;
    while (cursor !== resolve(root)) {
      try { if ((await lstat(cursor)).isSymbolicLink()) fail('destination_symlink'); } catch (err) { if (err.code !== 'ENOENT') throw err; }
      cursor = dirname(cursor);
    }
    let previous = null;
    try { previous = hash(await readFile(path)); } catch (err) { if (err.code !== 'ENOENT') throw err; }
    if (previous === row.digest) { items.push({ name: row.name, state: 'current', digest: previous }); continue; }
    if (request.op === 'check') { items.push({ name: row.name, state: previous ? 'drift' : 'missing', digest: previous }); continue; }
    if (!Object.hasOwn(row, 'expected') || row.expected !== previous) { items.push({ name: row.name, state: 'conflict', digest: previous }); continue; }
    if (typeof row.content !== 'string' || hash(Buffer.from(row.content, 'base64')) !== row.digest) fail('content_digest_rejected');
    await mkdir(dirname(path), { recursive: true });
    if (previous !== null) await copyFile(path, `${path}.bak-aos-${randomUUID()}`);
    const tmp = `${path}.${randomUUID()}.tmp`;
    await writeFile(tmp, Buffer.from(row.content, 'base64'), { flag: 'wx', mode: 0o600 });
    await rename(tmp, path);
    items.push({ name: row.name, state: hash(await readFile(path)) === row.digest ? 'updated' : 'failed', digest: row.digest });
  }
  return { schema: 'aos.fleet-target.v1', artifacts: items };
}
export async function discover(manifest, run = command) {
  exact(manifest, ['schema', 'targets']);
  if (manifest.schema !== 'aos.fleet-reconcile.v1' || !Array.isArray(manifest.targets) || !manifest.targets.length) fail('manifest_rejected');
  const targets = [];
  for (const host of manifest.targets) {
    exact(host, ['id', 'command', 'artifacts']);
    if (!id(host.id)) fail('target_rejected');
    try {
      const reply = await run(host.command, { schema: 'aos.fleet-target.v1', op: 'discover' });
      if (reply?.schema !== 'aos.fleet-target.v1' || !/^[a-f0-9]{64}$/.test(reply.toolkit_digest) || !Array.isArray(reply.sandboxes?.items) || !['observed', 'blocked'].includes(reply.sandboxes.state)) fail('discovery_reply_rejected');
      targets.push({ id: host.id, state: reply.sandboxes.state, toolkit_digest: reply.toolkit_digest,
        sandboxes: reply.sandboxes.items.map(item => {
          if (!id(item.name) || !['running', 'exited', 'created', 'paused', 'stopped', 'unknown'].includes(item.state)) fail('sandbox_identity_rejected');
          return { name: item.name, state: item.state, install_state: 'unchecked' };
        }) });
    } catch { targets.push({ id: host.id, state: 'blocked', sandboxes: [] }); }
  }
  return { schema: 'aos.fleet-discovery.v1', targets };
}
export async function reconcile(manifest, apply = false, run = command) {
  exact(manifest, ['schema', 'targets']);
  if (manifest.schema !== 'aos.fleet-reconcile.v1' || !Array.isArray(manifest.targets) || !manifest.targets.length) fail('manifest_rejected');
  const reports = [];
  for (const host of manifest.targets) {
    exact(host, ['id', 'command', 'artifacts']);
    if (!id(host.id) || !Array.isArray(host.artifacts) || !host.artifacts.length) fail('target_rejected');
    const artifacts = [];
    for (const row of host.artifacts) {
      artifact(row);
      if (!(await lstat(row.source)).isFile()) fail('source_not_regular');
      const bytes = await readFile(row.source);
      if (bytes.length > LIMIT || /(?:-----BEGIN .*PRIVATE KEY|(?:api[_-]?key|access[_-]?token|password|secret[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+/=_-]{16,})/i.test(bytes.toString())) fail('source_secret_rejected');
      // Applying only committed tracked source. Operator must explicitly
      // approve installed predecessor digests (or null for missing files).
      if (apply) {
        const git = spawn('git', ['diff', '--quiet', 'HEAD', '--', resolve(row.source)], { cwd: dirname(resolve(row.source)), stdio: 'ignore' });
        const code = await new Promise(done => { git.on('error', () => done(1)); git.on('close', done); });
        const tracked = spawn('git', ['ls-files', '--error-unmatch', resolve(row.source)], { cwd: dirname(resolve(row.source)), stdio: 'ignore' });
        const known = await new Promise(done => { tracked.on('error', () => done(1)); tracked.on('close', done); });
        if (code !== 0 || known !== 0) fail('source_not_committed');
      }
      artifacts.push({ name: row.name, destination: row.destination, digest: hash(bytes), ...(apply ? { content: bytes.toString('base64'), expected: row.expected } : {}) });
    }
    try {
      const reply = await run(host.command, { schema: 'aos.fleet-target.v1', op: apply ? 'apply' : 'check', artifacts });
      if (reply?.schema !== 'aos.fleet-target.v1' || !Array.isArray(reply.artifacts) || reply.artifacts.length !== artifacts.length) fail('target_reply_rejected');
      const items = artifacts.map(row => {
        const item = reply.artifacts.find(item => item?.name === row.name);
        if (!item || !['current', 'updated', 'drift', 'missing', 'conflict', 'failed'].includes(item.state) || (item.digest !== null && !/^[a-f0-9]{64}$/.test(item.digest))) fail('target_reply_rejected');
        if (['current', 'updated'].includes(item.state) && item.digest !== row.digest) fail('target_digest_rejected');
        return { name: row.name, state: item.state, digest: item.digest };
      });
      reports.push({ id: host.id, state: items.every(item => ['current', 'updated'].includes(item.state)) ? 'current' : 'drift', artifacts: items });
    } catch { reports.push({ id: host.id, state: 'blocked', error: 'target_probe_failed' }); }
  }
  return { schema: manifest.schema, mode: apply ? 'apply' : 'check', targets: reports, coverage: 'manifest-only' };
}
function options(args) {
  const opts = {};
  for (let index = 0; index < args.length; index++) {
    const key = args[index];
    if (['--apply', '--check', '--stdin'].includes(key)) { opts[key.slice(2)] = true; continue; }
    if (!['--manifest', '--identity', '--adapter', '--kernel-id', '--session', '--session-file', '--root'].includes(key) || !args[index + 1] || args[index + 1].startsWith('--')) fail('option_rejected');
    opts[key.slice(2)] = args[++index];
  }
  return opts;
}
async function stdin() {
  let data = '';
  for await (const chunk of process.stdin) { data += chunk; if (data.length > LIMIT) fail('stdin_limit'); }
  return JSON.parse(data);
}
export async function main(args) {
  if (args.includes('--help') || !args.length) {
    process.stderr.write('Usage: aos fleet discover --manifest <json>\n       aos fleet reconcile --manifest <json> [--check|--apply]\n       aos session bind --identity <json> --adapter <argv-json> --kernel-id <id>\n       aos session status --session <id> [--session-file <jsonl>]\n       aos-runtime.mjs target --root <home> --stdin\n--stdin accepts the manifest/identity instead of a file. No shell, credential provisioning, restart or implicit kernel.\n'); return;
  }
  const [plane, verb, ...rest] = args;
  const opts = options(plane === 'target' ? args.slice(1) : rest);
  if (opts.apply && opts.check) fail('mode_conflict');
  if (process.env.CARTESIA_EVENT_BUSES || process.env.CARTESIA_EVENT_BUS || process.env.CARTESIA_EVENT_PROFILE) fail('event_sink_unsupported');
  if ((process.env.CARTESIA_EVENT_SINKS ?? '').split(',').filter(Boolean).some(sink => !sink.startsWith('file:') || !safe(sink.slice(5)))) fail('event_sink_unsupported');
  const store = process.env.AOS_BINDINGS_HOME ?? join(homedir(), '.local/state/aos/bindings');
  let result;
  if (plane === 'fleet' && verb === 'discover') result = await discover(opts.stdin ? await stdin() : await json(opts.manifest));
  else if (plane === 'fleet' && verb === 'reconcile') result = await reconcile(opts.stdin ? await stdin() : await json(opts.manifest), !!opts.apply);
  else if (plane === 'target') result = await target(await stdin(), opts.root ?? homedir());
  else if (plane === 'session' && verb === 'bind') {
    const who = identity(opts.stdin ? await stdin() : await json(opts.identity));
    if (who.session_id.includes('/')) fail('session_id_rejected');
    const adapter = JSON.parse(opts.adapter ?? process.env.AOS_KERNEL_ADAPTER ?? 'null');
    result = await bind(who, adapter, opts['kernel-id']);
    await atomic(join(store, `${who.session_id}.json`), { identity: who, adapter, kernel_id: opts['kernel-id'], operation_id: result.operation_id });
    result = { schema: 'aos.session.v1', session_id: who.session_id, ...result };
  } else if (plane === 'session' && verb === 'status') {
    const sid = opts.session ?? process.env.PI_SESSION_ID;
    if (!id(sid) || sid.includes('/')) fail('session_id_rejected');
    let cfg; try { cfg = await json(join(store, `${sid}.json`)); } catch {}
    result = await status(sid, cfg, opts['session-file'] ?? cfg?.identity?.session_file ?? process.env.PI_SESSION_FILE);
  } else fail('command_rejected');
  await emit({ schema: 'aos.runtime-event.v1', plane, verb, at: new Date().toISOString(), state: result.kernel?.state ?? result.mode ?? 'observed' });
  process.stdout.write(JSON.stringify(result) + '\n');
  if (result.targets?.some(item => !['current', 'observed'].includes(item.state))) process.exitCode = 1;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) main(process.argv.slice(2)).catch(() => {
  // Do not print arbitrary exception messages (paths/adapter output can contain secrets).
  process.stderr.write('aos runtime: request failed; check schema, source, adapter and pinned identity\n');
  process.stdout.write('{"schema":"aos.runtime-error.v1","state":"blocked"}\n');
  process.exitCode = 2;
});
