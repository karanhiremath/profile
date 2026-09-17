#!/usr/bin/env node
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";

const runner = join(homedir(), ".pi", "agent", "extensions", "lib", "handoff-cursor-hook.ts");
const child = spawn(process.execPath, ["--experimental-strip-types", runner], {
	stdio: ["pipe", "inherit", "inherit"],
});
process.stdin.pipe(child.stdin);
child.on("close", (code) => {
	process.exit(code ?? 0);
});
child.on("error", () => {
	process.stdout.write("{}\n");
	process.exit(0);
});
