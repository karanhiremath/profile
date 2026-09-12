#!/usr/bin/env node
/**
 * Detached waiter for a fire-and-forget pi subagent.
 * Parent returns immediately; this process writes job-bus status on start/exit.
 */
import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

const JOB_SCHEMA = "pi.job-watcher.v1";
const HOST_BIND_ENV_PREFIXES = ["CURSOR_", "PI_CURSOR_", "MCP_", "__CURSOR_"];
const CHILD_ENV_ALLOW_KEYS = ["PI_CURSOR_LOCAL_RESUME"];
const CHILD_STRIP_ENV_KEYS = [
	"PI_SESSION_ID",
	"CDEV_SESSION_ID",
	"CDEV_SESSION_STEER_SID",
	"PI_JOBS_DIR",
	"PI_JOB_STREAM",
	"PI_JOB_STREAM_PATH",
	"PI_JOB_BUS_PATH",
];

function isHostBindEnvKey(key) {
	return HOST_BIND_ENV_PREFIXES.some((prefix) => key.startsWith(prefix));
}

function isAllowedChildEnvKey(key) {
	return CHILD_ENV_ALLOW_KEYS.includes(key);
}

const HOST_BIND_ENV_KEYS = ["CURSOR_AGENT", "CURSOR_TRACE_ID", "PI_CURSOR_SDK"];
const CHILD_NO_LOCAL_RESUME_FLAG = "--cursor-no-local-resume";

function isolatedChildEnv(env = process.env, extra = {}) {
	const out = { ...env };
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

function childPiArgs(args) {
	if (args.includes(CHILD_NO_LOCAL_RESUME_FLAG)) return args;
	return [CHILD_NO_LOCAL_RESUME_FLAG, ...args];
}

function isJsRuntimeCommand(command) {
	return /^(node|bun)(\.exe)?$/.test(path.basename(command).toLowerCase());
}

function resolveChildSpawn(command, args) {
	if (isJsRuntimeCommand(command)) {
		const without = args.filter((a) => a !== CHILD_NO_LOCAL_RESUME_FLAG);
		if (!without[0] || String(without[0]).startsWith("-")) {
			return { command: "pi", args: childPiArgs(without) };
		}
		return { command, args: [without[0], CHILD_NO_LOCAL_RESUME_FLAG, ...without.slice(1)] };
	}
	return { command, args: childPiArgs(args) };
}

function parseArgs(argv) {
	const out = { jobId: "", command: "", args: [], cwd: process.cwd(), metaPath: "" };
	const rest = [];
	for (let i = 0; i < argv.length; i++) {
		const a = argv[i];
		if (a === "--job-id") out.jobId = argv[++i];
		else if (a === "--cwd") out.cwd = argv[++i];
		else if (a === "--command") out.command = argv[++i];
		else if (a === "--meta") out.metaPath = argv[++i];
		else if (a === "--") {
			out.args = argv.slice(i + 1);
			break;
		} else rest.push(a);
	}
	if (!out.args.length && rest.length) out.args = rest;
	return out;
}

function appendLine(file, line) {
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.appendFileSync(file, line.endsWith("\n") ? line : `${line}\n`);
}

function writeRecord(meta, extra) {
	const record = {
		schema: JOB_SCHEMA,
		...meta,
		...extra,
		ts: new Date().toISOString(),
	};
	const line = JSON.stringify(record);
	fs.mkdirSync(path.dirname(record.statusPath), { recursive: true });
	fs.writeFileSync(record.statusPath, `${JSON.stringify(record, null, 2)}\n`);
	appendLine(record.eventsPath, line);
	if (record.namedStreamDir && record.jobId) {
		const namedStatus = path.join(record.namedStreamDir, `${record.jobId}.status.json`);
		const namedEvents = path.join(record.namedStreamDir, record.jobId, "events.jsonl");
		fs.mkdirSync(path.join(record.namedStreamDir, record.jobId), { recursive: true });
		fs.writeFileSync(namedStatus, `${JSON.stringify({ ...record, statusPath: namedStatus, eventsPath: namedEvents }, null, 2)}\n`);
		appendLine(namedEvents, line);
	}
	if (record.streamPath) appendLine(record.streamPath, line);
	if (record.busPath) appendLine(record.busPath, line);
	return record;
}

const opts = parseArgs(process.argv.slice(2));
if (!opts.jobId || !opts.command || !opts.metaPath) {
	console.error("usage: job-runner.mjs --job-id ID --command CMD --meta PATH -- [args...]");
	process.exit(2);
}

const meta = JSON.parse(fs.readFileSync(opts.metaPath, "utf8"));
const stdout = fs.openSync(meta.stdoutPath, "a");
const stderr = fs.openSync(meta.stderrPath, "a");
const childSpawn = resolveChildSpawn(opts.command, opts.args);
const child = spawn(childSpawn.command, childSpawn.args, {
	cwd: opts.cwd,
	env: isolatedChildEnv(process.env, { PI_CURSOR_LOCAL_RESUME: "0" }),
	stdio: ["ignore", stdout, stderr],
	detached: false,
});
fs.closeSync(stdout);
fs.closeSync(stderr);

writeRecord(meta, {
	type: "job.started",
	status: "running",
	pid: child.pid,
});

child.on("close", (code) => {
	const exitCode = code ?? 1;
	const ok = exitCode === 0;
	writeRecord(meta, {
		type: ok ? "job.finished" : "job.failed",
		status: ok ? "succeeded" : "failed",
		pid: child.pid,
		exitCode,
		message: ok ? "subagent finished" : `subagent exit ${exitCode}`,
	});
	process.exit(exitCode);
});

child.on("error", (err) => {
	writeRecord(meta, {
		type: "job.failed",
		status: "failed",
		exitCode: 127,
		message: String(err),
	});
	process.exit(127);
});
