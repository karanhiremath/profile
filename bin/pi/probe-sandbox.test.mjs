import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const root=dirname(fileURLToPath(import.meta.url));
function fixture(t) {
  const dir=mkdtempSync(join(tmpdir(),'pi-sandbox-test-'));
  t.after(()=>rmSync(dir,{recursive:true,force:true}));
  const fake=join(root,'fixtures/fake-podman.mjs');
  chmodSync(fake,0o755);
  symlinkSync(fake,join(dir,'podman'));
  const log=join(dir,'calls.jsonl');
  return {log,run:(args,extra={})=>spawnSync('bash',[join(root,'probe-sandbox'),'--container','fixture',...args],{
    encoding:'utf8',env:{...process.env,PATH:`${dir}:${process.env.PATH}`,FAKE_PODMAN_LOG:log,...extra}
  })};
}
test('dry-run and invalid version never invoke podman', t=>{
  const {run,log}=fixture(t);
  assert.equal(JSON.parse(run(['--dry-run']).stdout).mutated,false);
  assert.equal(run(['--install-cursor','latest']).status,2);
  assert.equal(existsSync(log),false);
});
test('install uses exact package source, no project approval, clean stdout', t=>{
  const {run,log}=fixture(t);
  const child=run(['--install-cursor','0.3.6']);
  assert.equal(child.status,0);
  assert.equal(JSON.parse(child.stdout).validated,false);
  assert.ok(child.stderr.includes('synthetic package install diagnostic'));
  const calls=readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(calls[1].includes('npm:pi-cursor-sdk@0.3.6'));
  assert.ok(calls[1].includes('--no-approve'));
});
test('stopped sandbox and failed install remain blocked', t=>{
  const {run}=fixture(t);
  assert.equal(JSON.parse(run([],{FAKE_PODMAN_RUNNING:'0'}).stdout).status,'blocked');
  const child=run(['--install-cursor','0.3.6'],{FAKE_PODMAN_INSTALL_EXIT:'1'});
  assert.equal(child.status,1);
  assert.equal(JSON.parse(child.stdout).status,'blocked');
});
test('fake end-to-end probe stages only source and removes it after exit', t=>{
  const {run,log}=fixture(t);
  const child=run(['--','--model','cursor/grok-4.6:fast','--bridge']);
  assert.equal(child.status,0);
  assert.equal(JSON.parse(child.stdout).mode,'fake');
  const calls=readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);
  assert.deepEqual(calls.map(args=>args[0]),['container','cp','exec','exec']);
  assert.ok(calls[2].includes('--bridge'));
  assert.ok(calls[3].includes('rm'));
  assert.ok(!calls.some(args=>args.some(arg=>/auth\.json|restart|kill/.test(arg))));
});
