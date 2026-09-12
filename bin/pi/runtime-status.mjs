#!/usr/bin/env node
// Read-only Pi inventory. Never opens auth files or invokes providers.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { isAbsolute, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
if (process.argv.includes('--help')) {
  process.stdout.write('Usage: runtime-status.mjs [--agent-dir DIR]\nReports Pi version, non-secret settings and installed paths only.\n');
  process.exit(0);
}
const argv=process.argv.slice(2);
if (argv.length && (argv.length!==2 || argv[0]!=='--agent-dir')) {
  process.stdout.write('{"schema":"pi.runtime.v1","status":"blocked","reason":"invalid_arguments"}\n');
  process.exit(2);
}
const root=resolve(argv[1] || process.env.PI_CODING_AGENT_DIR || join(homedir(),'.pi/agent'));
try {
  const file=join(root,'settings.json');
  const settings=existsSync(file)?JSON.parse(readFileSync(file,'utf8')):{};
  const child=spawnSync('pi',['--version'],{encoding:'utf8'});
  const version=String(child.stdout||'').trim();
  const packages=(Array.isArray(settings.packages)?settings.packages:[]).map(entry=>{
    const source=typeof entry==='string'?entry:entry?.source;
    return typeof source==='string'?{source,exists:/^(npm:|git:|https?:|ssh:)/.test(source)?null:existsSync(isAbsolute(source)?source:resolve(root,source))}:{invalid:true};
  });
  const extensions=existsSync(join(root,'extensions'))?readdirSync(join(root,'extensions')).sort():[];
  process.stdout.write(JSON.stringify({schema:'pi.runtime.v1',version:/^\d+\.\d+\.\d+(?:[-+][\w.-]+)?$/.test(version)?version:null,
    binaryAvailable:child.status===0,agentDir:root,defaultProvider:settings.defaultProvider,defaultModel:settings.defaultModel,packages,extensions})+'\n');
} catch {
  process.stdout.write('{"schema":"pi.runtime.v1","status":"blocked","reason":"inventory_failed"}\n');
  process.exitCode=1;
}
