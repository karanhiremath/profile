import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { installRuntime, RUNTIME_FILES } from './install-handoff-runtime.mjs';
const source=resolve(dirname(fileURLToPath(import.meta.url)), '../../config/pi/extensions');
function fixture(t) {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'pi-handoff-runtime-test-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  return root;
}
test('dry-run is clean; complete installed closure imports without ambient modules', async t=>{
  const root=fixture(t), dest=join(root,'extensions');
  assert.equal(installRuntime(source,dest).applied,false);
  assert.equal(existsSync(dest),false);
  const report=installRuntime(source,dest,true);
  assert.equal(report.files.length,RUNTIME_FILES.length);
  const jobs=await import(pathToFileURL(join(dest,'subagent/jobs.ts')).href);
  const invocation=await import(pathToFileURL(join(dest,'subagent/pi-invocation.ts')).href);
  assert.equal(jobs.JOB_SCHEMA,'pi.job-watcher.v1');
  assert.equal(jobs.namedStreamDir('lane',root,'project'),join(root,'.pi/agent/jobs/projects/project/streams/lane'));
  assert.deepEqual(invocation.resolveChildSpawn('node',['app.js','-p','hello']),{command:'node',args:['app.js','--cursor-no-local-resume','-p','hello']});
  assert.ok(existsSync(join(dest,'subagent/job-runner.mjs')));
  assert.ok(installRuntime(source,dest,true).files.every(f=>f.action==='unchanged'));
});
test('preserves host overrides and never touches credential files', t=>{
  const root=fixture(t), dest=join(root,'extensions');
  installRuntime(source,dest,true);
  writeFileSync(join(dest,'subagent/jobs.ts'),'operator override');
  writeFileSync(join(root,'auth.json'),'credential-fixture');
  const result=installRuntime(source,dest,true);
  assert.equal(result.files.find(f=>f.name==='subagent/jobs.ts').action,'preserved_override');
  assert.equal(readFileSync(join(dest,'subagent/jobs.ts'),'utf8'),'operator override');
  assert.equal(readFileSync(join(root,'auth.json'),'utf8'),'credential-fixture');
});
test('rejects missing sources and symlink destinations before writes', t=>{
  const root=fixture(t), dest=join(root,'extensions');
  assert.throws(()=>installRuntime(root,dest,true));
  assert.equal(existsSync(dest),false);
  symlinkSync(root,dest);
  assert.throws(()=>installRuntime(source,dest,true));
});
test('telemetry redacts the whole recognized value, not just its prefix', async()=>{
  const {redactSummary}=await import(pathToFileURL(join(source,'lib/agent-otel.ts')).href);
  const result=redactSummary('token=opaque-fixture sk-fixture123 ghp_fixture456 xoxb-fixture789 Bearer opaque-fixture2');
  for(const value of ['opaque-fixture','fixture123','fixture456','fixture789']) assert.ok(!result.includes(value));
});
