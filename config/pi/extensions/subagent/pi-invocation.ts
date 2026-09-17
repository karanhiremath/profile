import * as fs from "node:fs";
import * as path from "node:path";

export const HOST_BIND_ENV_KEYS = ["CURSOR_AGENT", "CURSOR_TRACE_ID", "PI_CURSOR_SDK"] as const;
// Live Cursor host leak set is prefix-based: CURSOR_* (incl. CONVERSATION_ID,
// RIPGREP_PATH), PI_CURSOR_*, MCP_*, and __CURSOR_* restore hooks that re-export
// CURSOR_CONVERSATION_ID. Detection stays on HOST_BIND_ENV_KEYS (parent env).
export const HOST_BIND_ENV_PREFIXES = ["CURSOR_", "PI_CURSOR_", "MCP_", "__CURSOR_"] as const;
export const CHILD_ENV_ALLOW_KEYS = ["PI_CURSOR_LOCAL_RESUME"] as const;
/** Owner inbox / session bind. A child that keeps these watches the parent job dir and steers into its own -p turn. */
export const CHILD_STRIP_ENV_KEYS = [
	"PI_SESSION_ID",
	"CDEV_SESSION_ID",
	"CDEV_SESSION_STEER_SID",
	"PI_JOBS_DIR",
	"PI_JOB_STREAM",
	"PI_JOB_STREAM_PATH",
	"PI_JOB_BUS_PATH",
] as const;

export function isHostBindEnvKey(key: string): boolean {
	return HOST_BIND_ENV_PREFIXES.some((prefix) => key.startsWith(prefix));
}

function isAllowedChildEnvKey(key: string): boolean {
	return (CHILD_ENV_ALLOW_KEYS as readonly string[]).includes(key);
}

export const CHILD_NO_LOCAL_RESUME_FLAG = "--cursor-no-local-resume";

export function childPiArgs(args: string[]): string[] {
	if (args.includes(CHILD_NO_LOCAL_RESUME_FLAG)) return args;
	return [CHILD_NO_LOCAL_RESUME_FLAG, ...args];
}

export function isJsRuntimeCommand(command: string): boolean {
	return /^(node|bun)(\.exe)?$/.test(path.basename(command).toLowerCase());
}

/** Place --cursor-no-local-resume where the child CLI sees it, never as a node/bun option. */
export function childSpawnArgs(command: string, args: string[]): string[] {
	return resolveChildSpawn(command, args).args;
}

/** node/bun + flag-only argv is exit 9 (`bad option: --cursor-no-local-resume`). Use pi. */
export function resolveChildSpawn(
	command: string,
	args: string[],
): { command: string; args: string[] } {
	if (isJsRuntimeCommand(command)) {
		const without = args.filter((a) => a !== CHILD_NO_LOCAL_RESUME_FLAG);
		if (!without[0] || without[0].startsWith("-")) {
			return { command: "pi", args: childPiArgs(without) };
		}
		return { command, args: [without[0], CHILD_NO_LOCAL_RESUME_FLAG, ...without.slice(1)] };
	}
	return { command, args: childPiArgs(args) };
}

export function isolatedChildEnv(
	env: NodeJS.ProcessEnv = process.env,
	extra: NodeJS.ProcessEnv = {},
): NodeJS.ProcessEnv {
	const out: NodeJS.ProcessEnv = { ...env };
	for (const key of Object.keys(out)) {
		if (isHostBindEnvKey(key)) delete out[key];
	}
	for (const key of CHILD_STRIP_ENV_KEYS) delete out[key];
	for (const [key, value] of Object.entries(extra)) {
		if (value === undefined) continue;
		if (isHostBindEnvKey(key) && !isAllowedChildEnvKey(key)) continue;
		out[key] = value;
	}
	for (const key of HOST_BIND_ENV_KEYS) delete out[key];
	if (out.PI_JOB_BUS_STEER_SELF === undefined) out.PI_JOB_BUS_STEER_SELF = "0";
	if (out.PI_CURSOR_LOCAL_RESUME === undefined) out.PI_CURSOR_LOCAL_RESUME = "0";
	return out;
}

export function isHostBoundScript(
	script: string,
	env: NodeJS.ProcessEnv = process.env,
): boolean {
	if (HOST_BIND_ENV_KEYS.some((key) => Boolean(env[key]))) return true;
	const full = script.toLowerCase();
	return full.includes("cursor") || full.includes("pi-cursor");
}

export function resolvePiInvocation(input: {
	args: string[];
	currentScript?: string;
	execPath: string;
	env?: NodeJS.ProcessEnv;
	scriptExists?: boolean;
}): { command: string; args: string[] } {
	const script = input.currentScript || "";
	const exists = input.scriptExists ?? false;
	const env = input.env || {};
	const isBunVirtual = script.startsWith("/$bunfs/root/");
	if (script && !isBunVirtual && exists && !isHostBoundScript(script, env)) {
		return { command: input.execPath, args: [script, ...childPiArgs(input.args)] };
	}
	const execName = path.basename(input.execPath).toLowerCase();
	const isGenericRuntime = /^(node|bun)(\.exe)?$/.test(execName);
	if (!isGenericRuntime) {
		return { command: input.execPath, args: childSpawnArgs(input.execPath, input.args) };
	}
	return { command: "pi", args: childPiArgs(input.args) };
}

export function getPiInvocation(args: string[]): { command: string; args: string[] } {
	const currentScript = process.argv[1];
	return resolvePiInvocation({
		args,
		currentScript,
		execPath: process.execPath,
		env: process.env,
		scriptExists: Boolean(currentScript && fs.existsSync(currentScript)),
	});
}
