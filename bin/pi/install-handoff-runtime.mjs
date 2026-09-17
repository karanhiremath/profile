#!/usr/bin/env node
/** Install the complete generic handoff support closure; never overwrite host overrides. */
import { copyFileSync, constants, existsSync, lstatSync, mkdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const RUNTIME_FILES = [
  'subagent/jobs.ts', 'subagent/job-runner.mjs', 'subagent/pi-invocation.ts',
  'lib/job-bus-project.ts', 'lib/agent-otel.ts',
];
export const COMPONENTS = {
  handoff: RUNTIME_FILES,
  'cursor-abort-retry': ['cursor-abort-retry.ts', 'lib/cursor-abort-retry.ts'],
  'job-bus': ['job-bus.ts', ...RUNTIME_FILES, 'lib/job-bus-ack.ts', 'lib/job-bus-target.ts',
    'lib/fleet-workspace.ts', 'lib/harness-remotes.ts', 'lib/stdio-socket.ts', 'lib/agent-comms.ts'],
};
const sha = file => createHash('sha256').update(readFileSync(file)).digest('hex');

function assertPlainDirectory(dir) {
  let cursor = resolve(dir);
  while (true) {
    if (existsSync(cursor)) {
      const stat = lstatSync(cursor);
      if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('unsafe_directory');
    }
    const parent = dirname(cursor);
    if (parent === cursor) return;
    cursor = parent;
  }
}

export function installRuntime(source, destination, apply = false, components = ['handoff']) {
  source = resolve(source); destination = resolve(destination);
  assertPlainDirectory(destination);
  if (!components.length || components.some(name => !Object.hasOwn(COMPONENTS, name))) throw new Error('unknown_component');
  const files = [...new Set(components.flatMap(name => COMPONENTS[name]))].map(name => {
    const from = join(source, name), to = join(destination, name);
    if (!existsSync(from) || !lstatSync(from).isFile() || lstatSync(from).isSymbolicLink()) throw new Error('missing_or_unsafe_source');
    assertPlainDirectory(dirname(to));
    let exists = false;
    try {
      const stat = lstatSync(to);
      if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('unsafe_destination');
      exists = true;
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    return { name, action: exists ? (sha(from) === sha(to) ? 'unchanged' : 'preserved_override') : 'install', sha256: sha(from) };
  });
  // Preflight ALL files before the first mutation. Existing files are never replaced.
  if (apply) {
    for (const file of files.filter(file => file.action === 'install')) {
      const target = join(destination, file.name);
      assertPlainDirectory(dirname(target));
      mkdirSync(dirname(target), {recursive:true, mode:0o700});
      copyFileSync(join(source, file.name), target, constants.COPYFILE_EXCL);
    }
  }
  return {schema:'pi.handoff-runtime.v1', applied:apply, files};
}

function main(argv) {
  if (argv.includes('--help')) {
    process.stdout.write('Usage: install-handoff-runtime.mjs [--source EXTENSIONS] [--destination EXTENSIONS] [--component handoff|cursor-abort-retry|job-bus] [--apply]\nDefault is dry-run. Adds missing support files only; preserves existing files, settings, credentials and sessions.\n');
    return;
  }
  let source = resolve(dirname(fileURLToPath(import.meta.url)), '../../config/pi/extensions');
  let destination = join(process.env.PI_CODING_AGENT_DIR || join(homedir(), '.pi/agent'), 'extensions');
  let apply = false;
  const components = [];
  for (let i=0; i<argv.length; i++) {
    if (argv[i] === '--apply') {apply=true; continue;}
    if (!['--source','--destination','--component'].includes(argv[i]) || !argv[i+1] || argv[i+1].startsWith('--')) throw new Error('invalid_arguments');
    if (argv[i] === '--component') components.push(argv[++i]);
    else if (argv[i] === '--source') source=argv[++i]; else destination=argv[++i];
  }
  process.stdout.write(JSON.stringify(installRuntime(source,destination,apply,components.length ? components : ['handoff']))+'\n');
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {main(process.argv.slice(2));} catch {
    process.stdout.write(JSON.stringify({schema:'pi.handoff-runtime.v1',status:'blocked',reason:'invalid_arguments_or_runtime_files'})+'\n');
    process.exitCode=1;
  }
}
