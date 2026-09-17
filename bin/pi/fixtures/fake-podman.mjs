#!/usr/bin/env node
// Offline sandbox wrapper fixture. Never invokes a container or provider.
import { appendFileSync } from 'node:fs';
const args=process.argv.slice(2);
if (process.env.FAKE_PODMAN_LOG) appendFileSync(process.env.FAKE_PODMAN_LOG,JSON.stringify(args)+'\n');
if (args[0]==='container' && args[1]==='inspect') {
  process.stdout.write(process.env.FAKE_PODMAN_RUNNING==='0'?'false\n':'true\n');
} else if(args[0]==='cp') {
  process.exitCode=0;
} else if(args[0]==='exec' && args.includes('pi') && args.includes('install')) {
  process.stdout.write('synthetic package install diagnostic\n');
  process.exitCode=Number(process.env.FAKE_PODMAN_INSTALL_EXIT || 0);
} else if(args[0]==='exec' && args.includes('node')) {
  process.stdout.write('{"schema":"harness.pi-toolcall.v1","status":"passed","mode":"fake"}\n');
} else if(args[0]==='exec' && args.includes('rm')) {
  process.exitCode=0;
} else {
  process.exitCode=2;
}
