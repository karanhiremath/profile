import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm, mkdir, symlink, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { bind, projectBinding, usage, handoff, target, reconcile, discover, telemetry, status, command } from './aos-runtime.mjs';
const root = dirname(fileURLToPath(import.meta.url));
const hash = data => createHash('sha256').update(data).digest('hex');
const who = { schema: 'aos.identity.v1', session_id: 'native-1', harness: 'pi', host: 'host-a', profile: 'implementor', profile_digest: 'a'.repeat(64), worktree: '/repo', project: 'project-a' };
function reply(operation, extra = {}) {
  return { schema: 'aos.kernel-binding.v1', kernel_id: 'original', observed_at: new Date().toISOString(), heartbeat_at: new Date().toISOString(), binding: { ...who, operation_id: operation, accepted: true }, graph: { kernel_id: 'original', session_id: who.session_id, project: who.project, nodes: [{ id: 'n1', label: 'Worker', state: 'running', secret: 'NEVER' }], edges: [] }, ...extra };
}
async function temp(t) { const dir = await mkdtemp(join(tmpdir(), 'aos-runtime-')); t.after(() => rm(dir, { recursive: true, force: true })); return dir; }
test('discovery includes stopped sandboxes; unavailable inventory is not empty-success', async () => {
  const manifest = { schema: 'aos.fleet-reconcile.v1', targets: [{ id: 'host-a', command: ['target'] }] };
  const got = await discover(manifest, async (_, request) => target(request, '/fixture', async () => [{ Names: ['box-a'], State: 'running' }, { Names: ['box-b'], State: 'exited' }]));
  assert.equal(got.targets[0].state, 'observed');
  assert.deepEqual(got.targets[0].sandboxes.map(row => row.state), ['running', 'exited']);
  const blocked = await discover(manifest, async (_, request) => target(request, '/fixture', async () => { throw new Error('custody blocked'); }));
  assert.equal(blocked.targets[0].state, 'blocked');
  const empty = await discover(manifest, async (_, request) => target(request, '/fixture', async () => []));
  assert.equal(empty.targets[0].state, 'observed'); assert.deepEqual(empty.targets[0].sandboxes, []);
});
test('binding requires receipt then independent matching native identity and graph', async () => {
  const calls = [];
  const got = await bind(who, ['adapter'], 'original', async (_, request) => {
    calls.push(request.op);
    return request.op === 'bind' ? { schema: request.schema, kernel_id: 'original', accepted: true, operation_id: request.operation_id } : reply(request.operation_id);
  });
  assert.deepEqual(calls, ['bind', 'observe']);
  assert.equal(got.kernel.state, 'attached'); assert.equal(got.graph.state, 'live');
  assert.equal(JSON.stringify(got).includes('NEVER'), false);
});
test('reject mismatched kernel, native identity, operation, future or stale heartbeat', async () => {
  const operation = 'op';
  for (const key of ['session_id', 'harness', 'host', 'profile', 'profile_digest', 'worktree', 'project', 'operation_id']) {
    const data = reply(operation); data.binding[key] = 'wrong';
    assert.throws(() => projectBinding(data, who, 'original', operation));
  }
  assert.throws(() => projectBinding(reply(operation), who, 'replacement', operation));
  for (const at of [new Date(Date.now() - 60000), new Date(Date.now() + 60000)]) {
    assert.equal(projectBinding(reply(operation, { heartbeat_at: at.toISOString() }), who, 'original', operation).kernel.state, 'stale');
  }
  const data = reply(operation); data.graph.session_id = 'other';
  assert.equal(projectBinding(data, who, 'original', operation).graph.state, 'unavailable');
  await assert.rejects(() => bind(who, ['adapter'], 'original', async () => ({ accepted: true })), /receipt/);
  await assert.rejects(() => bind(who, ['adapter', '--token=SECRET'], 'original'), /public_adapter/);
});
test('both token formats; persistence authoritative, IDs deduped; cumulative != context', async t => {
  const dir = await temp(t); const path = join(dir, 'session.jsonl');
  const data = { input: 10, output: 2, cacheRead: 5, cacheWrite: 1, totalTokens: 18 };
  const msg = { id: 'm1', role: 'assistant', timestamp: 1000, usage: data };
  await writeFile(path, [JSON.stringify({ type: 'session', id: who.session_id }), JSON.stringify({ type: 'message_end', message: msg }), JSON.stringify({ type: 'message', message: msg }), JSON.stringify({ type: 'message', message: msg }), 'broken'].join('\n'));
  const got = await usage(path, who.session_id);
  assert.deepEqual(got.tokens, { input: 10, output: 2, cache_read: 5, cache_write: 1, total: 18, turns: 1 });
  assert.equal(got.context.state, 'unavailable');
  await assert.rejects(() => usage(path, 'other'), /session_mismatch/);
  await writeFile(path, JSON.stringify({ type: 'message_end', message: { ...msg, usage: { input: 2, output: 3, context_used: 600, context_max: 1000 } } }));
  const streamed = await usage(path, who.session_id);
  assert.equal(streamed.tokens.input, 2); assert.equal(streamed.tokens.cache_read, null); assert.equal(streamed.context.percent, 60);
});
test('partial cache reporting stays unknown; binding keys have stable order', async t => {
  const dir = await temp(t); const path = join(dir, 'session.jsonl');
  await writeFile(path, [{ type: 'message', message: { id: 'a', role: 'assistant', usage: { input: 1, output: 1, cacheRead: 4 } } }, { type: 'message', message: { id: 'b', role: 'assistant', usage: { input: 2, output: 2 } } }].map(JSON.stringify).join('\n'));
  assert.equal((await usage(path, who.session_id)).tokens.cache_read, null);
  const operations = [];
  const run = async (_, request) => {
    operations.push(request.operation_id);
    return request.op === 'bind' ? { schema: request.schema, kernel_id: 'original', operation_id: request.operation_id, accepted: true } : reply(request.operation_id);
  };
  await bind(who, ['adapter'], 'original', run);
  await bind(Object.fromEntries(Object.entries(who).reverse()), ['adapter'], 'original', run);
  assert.equal(new Set(operations).size, 1);
});
test('native kernel telemetry is correlated, fresh and public-only', () => {
  const value = { schema: 'aos.session-telemetry.v1', session_id: who.session_id, observed_at: new Date().toISOString(), tokens: { input: 10, output: 2, turns: 1, cache_read: 5, secret: 'NEVER' }, context: { used: 600, limit: 1000 }, secret: 'NEVER' };
  const got = telemetry(value, who.session_id);
  assert.equal(got.context.percent, 60); assert.equal(got.tokens.cache_write, null); assert.equal(JSON.stringify(got).includes('NEVER'), false);
  assert.equal(telemetry(value, 'other'), null);
  assert.equal(telemetry({ ...value, observed_at: new Date(Date.now() - 60000).toISOString() }, who.session_id), null);
});
test('handoff queue is not completion, identity mismatch fails closed', () => {
  const prep = { schema: 'pi.handoff-prep.v1', source_session_id: who.session_id, phase: 'queued', child_session_id: 'child-1' };
  assert.equal(handoff(prep, who.session_id).phase, 'queued');
  assert.equal(handoff(prep, 'other').phase, 'unavailable');
  assert.equal(handoff({ ...prep, phase: 'switched' }, who.session_id).phase, 'switched');
});
test('target check/apply, predecessor guard, backup and digest readback', async t => {
  const dir = await temp(t); const path = join(dir, 'profile.yaml'); await writeFile(path, 'old');
  const row = { name: 'profile', destination: 'profile.yaml', digest: hash('new'), content: Buffer.from('new').toString('base64'), expected: hash('old') };
  const request = { schema: 'aos.fleet-target.v1', op: 'check', artifacts: [row] };
  assert.equal((await target(request, dir)).artifacts[0].state, 'drift');
  assert.equal(await readFile(path, 'utf8'), 'old');
  assert.equal((await target({ ...request, op: 'apply', artifacts: [{ ...row, expected: null }] }, dir)).artifacts[0].state, 'conflict');
  assert.equal((await target({ ...request, op: 'apply' }, dir)).artifacts[0].state, 'updated');
  assert.equal(await readFile(path, 'utf8'), 'new');
  const backup = (await readdir(dir)).find(name => name.includes('.bak-aos-'));
  assert.equal(await readFile(join(dir, backup), 'utf8'), 'old');
  assert.equal((await target({ ...request, op: 'apply' }, dir)).artifacts[0].state, 'current');
});
test('reject escapes, symlinks, secret artifacts and bad content digests', async t => {
  const dir = await temp(t); const outside = await temp(t); await symlink(outside, join(dir, 'linked'));
  const row = { name: 'profile', destination: '../escape', digest: hash('new'), content: Buffer.from('bad').toString('base64'), expected: null };
  const request = { schema: 'aos.fleet-target.v1', op: 'apply', artifacts: [row] };
  for (const dest of ['../escape', '/absolute', 'linked/escape', 'auth.json', '.env.local']) {
    await assert.rejects(() => target({ ...request, artifacts: [{ ...row, destination: dest }] }, dir));
  }
  await assert.rejects(() => target({ ...request, artifacts: [{ ...row, destination: 'profile.yaml' }] }, dir), /digest/);
});
test('reconcile complete fake target pipeline; failures explicit; source must be committed', async t => {
  const dir = await temp(t); const source = join(dir, 'profile.yaml'); await writeFile(source, 'name: test');
  const manifest = { schema: 'aos.fleet-reconcile.v1', targets: [{ id: 'host-a', command: ['target'], artifacts: [{ name: 'profile', source, destination: 'installed.yaml', expected: null }] }] };
  const got = await reconcile(manifest, false, async (_, request) => target(request, dir));
  assert.equal(got.targets[0].artifacts[0].state, 'missing');
  assert.equal((await reconcile(manifest, false, async () => { throw new Error('TOKEN'); })).targets[0].state, 'blocked');
  await assert.rejects(() => reconcile(manifest, true), /source_not_committed/);
  spawnSync('git', ['init', '-q'], { cwd: dir });
  spawnSync('git', ['add', 'profile.yaml'], { cwd: dir });
  spawnSync('git', ['-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], { cwd: dir });
  const applied = await reconcile(manifest, true, async (_, request) => target(request, dir));
  assert.equal(applied.targets[0].state, 'current');
  await writeFile(source, 'dirty'); await assert.rejects(() => reconcile(manifest, true), /source_not_committed/);
});
test('schema rejection, source secret redaction, no fabricated attached state', async t => {
  const dir = await temp(t); const source = join(dir, 'bad.yaml'); await writeFile(source, 'api_key: SECRETSECRETSECRETSECRET');
  const manifest = { schema: 'aos.fleet-reconcile.v1', targets: [{ id: 'host', command: ['target'], artifacts: [{ name: 'bad', source, destination: 'installed.yaml' }] }] };
  await assert.rejects(() => reconcile(manifest), /source_secret/);
  await assert.rejects(() => reconcile({ ...manifest, extra: true }), /schema/);
  const got = await status(who.session_id, undefined, undefined, dir);
  assert.equal(got.kernel.state, 'unbound'); assert.equal(got.tokens, null);
});
test('secret paths and symlinked session files are never read', async t => {
  const dir = await temp(t); const path = join(dir, 'auth.json'); await writeFile(path, 'SECRET');
  await assert.rejects(() => usage(path, who.session_id), /protected_usage_path/);
  await symlink(path, join(dir, 'session.jsonl'));
  await assert.rejects(() => usage(join(dir, 'session.jsonl'), who.session_id), /protected_usage_path/);
});
test('argv adapter rejects prose/nonzero and never relays secret stderr', async () => {
  await assert.rejects(() => command([process.execPath, '-e', 'process.stderr.write("SECRET");process.exit(1)'], {}), /adapter_failed/);
  await assert.rejects(() => command([process.execPath, '-e', 'process.stdout.write("prose")'], {}), /invalid_json/);
});
test('CLI structured stdin/stdout; multi-sink events contain no contents', async t => {
  const dir = await temp(t); const source = join(dir, 'profile.yaml'); await writeFile(source, 'name: test');
  const a = join(dir, 'a.ndjson'); const b = join(dir, 'b.ndjson');
  const manifest = { schema: 'aos.fleet-reconcile.v1', targets: [{ id: 'local', command: [process.execPath, join(root, 'aos-runtime.mjs'), 'target', '--root', dir, '--stdin'], artifacts: [{ name: 'profile', source, destination: 'installed.yaml' }] }] };
  const run = spawnSync(process.execPath, [join(root, 'aos-runtime.mjs'), 'fleet', 'reconcile', '--stdin'], { input: JSON.stringify(manifest), encoding: 'utf8', env: { ...process.env, CARTESIA_EVENT_SINKS: `file:${a},file:${b}` } });
  assert.equal(run.status, 1); assert.equal(JSON.parse(run.stdout).targets[0].state, 'drift');
  assert.deepEqual(await readFile(a, 'utf8'), await readFile(b, 'utf8'));
  assert.equal((await readFile(a, 'utf8')).includes('name: test'), false);
  const invalid = spawnSync(process.execPath, [join(root, 'aos-runtime.mjs'), 'fleet', 'reconcile', '--stdin'], { input: '{"schema":"wrong"}', encoding: 'utf8' });
  assert.equal(invalid.status, 2); assert.equal(JSON.parse(invalid.stdout).state, 'blocked');
});
