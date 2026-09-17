/**
 * Shared job-bus records for fire-and-forget subagents and watchers.
 * Schema: pi.job-watcher.v1
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
	jobsHostRoot,
	legacyLaneDir,
	projectLaneDir,
	resolveJobProject,
} from "../lib/job-bus-project.ts";
import { emitJobOtel } from "../lib/agent-otel.ts";

export const JOB_SCHEMA = "pi.job-watcher.v1";

export type JobStatus = "running" | "succeeded" | "failed";
export type JobEventType = "job.started" | "job.heartbeat" | "job.finished" | "job.failed";

export type JobRecord = {
	schema: typeof JOB_SCHEMA;
	jobId: string;
	source: string;
	type: JobEventType;
	status: JobStatus;
	agent?: string;
	task?: string;
	cwd?: string;
	pid?: number;
	exitCode?: number;
	ts: string;
	stdoutPath?: string;
	stderrPath?: string;
	eventsPath?: string;
	statusPath?: string;
	message?: string;
	stream?: string;
	project?: string;
	ownerSid?: string;
	sessionId?: string;
	targetSid?: string;
};

function safeSessionId(raw: string): string {
	return raw.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 128);
}

export function sessionId(): string {
	for (const key of ["PI_SESSION_ID", "CDEV_SESSION_STEER_SID", "CDEV_SESSION_ID"]) {
		const value = (process.env[key] || "").trim();
		if (value) return safeSessionId(value);
	}
	return "";
}

export function jobsRoot(home = os.homedir()): string {
	if (process.env.PI_JOBS_DIR) return process.env.PI_JOBS_DIR;
	const sid = sessionId();
	if (sid) return path.join(home, ".pi", "agent", "jobs", "sessions", sid);
	return path.join(home, ".pi", "agent", "jobs", "unscoped");
}

export function streamPath(home = os.homedir()): string {
	const override = process.env.PI_JOB_STREAM_PATH || process.env.PI_JOB_STREAM;
	if (override) return override;
	const sid = sessionId();
	if (sid) return path.join(home, ".pi", "agent", "job-watcher-streams", "sessions", `${sid}.jsonl`);
	return path.join(home, ".pi", "agent", "job-watcher-streams", "unscoped.jsonl");
}

export function extraBusPath(): string | undefined {
	return process.env.PI_JOB_BUS_PATH || undefined;
}

export function streamsRoot(home = os.homedir()): string {
	if (process.env.PI_JOB_STREAMS_DIR) return process.env.PI_JOB_STREAMS_DIR;
	return path.join(jobsHostRoot(home), "streams");
}

/** Project lane by default. Pass project="" and use streamsRoot only via PI_JOB_STREAMS_DIR. */
export function namedStreamDir(name: string, home = os.homedir(), project?: string): string {
	if (process.env.PI_JOB_STREAMS_DIR) return path.join(process.env.PI_JOB_STREAMS_DIR, safeSessionId(name));
	const slug = project || resolveJobProject({ cwd: process.cwd() });
	return projectLaneDir(slug, name, jobsHostRoot(home));
}

export function defaultStreamName(source = "", jobId = "", explicit = ""): string {
	if (explicit.trim()) return safeSessionId(explicit);
	const env = (process.env.PI_JOB_STREAM_NAME || "").trim();
	if (env) return safeSessionId(env);
	const src = source.toLowerCase();
	if (src.includes("assembler")) return "assembler";
	if (src.includes("cloudbuild")) return "cloudbuild";
	if (src.includes("subagent")) return "subagent";
	return safeSessionId(jobId || "job");
}

export function newJobId(prefix = "subagent"): string {
	const rand = Math.random().toString(36).slice(2, 8);
	return `${prefix}-${Date.now()}-${rand}`;
}

export function jobDir(jobId: string, home = os.homedir()): string {
	return path.join(jobsRoot(home), jobId);
}

export function statusPathFor(jobId: string, home = os.homedir()): string {
	return path.join(jobsRoot(home), `${jobId}.status.json`);
}

export function eventsPathFor(jobId: string, home = os.homedir()): string {
	return path.join(jobDir(jobId, home), "events.jsonl");
}

export function ensureJobDir(jobId: string, home = os.homedir()): string {
	const dir = jobDir(jobId, home);
	fs.mkdirSync(dir, { recursive: true });
	fs.mkdirSync(path.dirname(streamPath(home)), { recursive: true });
	fs.mkdirSync(jobsRoot(home), { recursive: true });
	return dir;
}

function appendLine(file: string, line: string): void {
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.appendFileSync(file, line.endsWith("\n") ? line : `${line}\n`);
}

function writeInbox(root: string, record: JobRecord): JobRecord {
	const statusPath = path.join(root, `${record.jobId}.status.json`);
	const eventsPath = path.join(root, record.jobId, "events.jsonl");
	const filled: JobRecord = { ...record, statusPath, eventsPath };
	const line = JSON.stringify(filled);
	fs.mkdirSync(path.join(root, record.jobId), { recursive: true });
	fs.writeFileSync(statusPath, `${JSON.stringify(filled, null, 2)}\n`);
	appendLine(eventsPath, line);
	return filled;
}

export function writeJobRecord(record: JobRecord, home = os.homedir()): JobRecord {
	const stream = defaultStreamName(record.source || "", record.jobId, record.stream || "");
	const project = resolveJobProject(record);
	const sid = record.ownerSid || record.sessionId || sessionId();
	const filled = writeInbox(jobsRoot(home), {
		...record,
		stream,
		project,
		...(sid ? { ownerSid: record.ownerSid || sid, sessionId: record.sessionId || sid } : {}),
	});
	try {
		writeInbox(namedStreamDir(stream, home, project), filled);
	} catch {
		/* named stream is best-effort */
	}
	if (String(process.env.PI_JOB_BUS_MIRROR_GLOBAL || "").trim() === "1") {
		try {
			writeInbox(legacyLaneDir(stream, jobsHostRoot(home)), filled);
		} catch {
			/* legacy mirror is opt-in */
		}
	}
	const line = JSON.stringify(filled);
	appendLine(streamPath(home), line);
	const extra = extraBusPath();
	if (extra) appendLine(extra, line);
	emitJobOtel(filled.type, {
		runtime: "pi",
		session_id: filled.sessionId || filled.ownerSid,
		project: filled.project,
		job_id: filled.jobId,
		stream: filled.stream,
		status: filled.status,
		summary: filled.message || filled.task || filled.type,
		raw_ref: filled.statusPath,
	}, { home });
	return filled;
}

export function readJobStatus(jobId: string, home = os.homedir()): JobRecord | undefined {
	const p = statusPathFor(jobId, home);
	try {
		return JSON.parse(fs.readFileSync(p, "utf8")) as JobRecord;
	} catch {
		return undefined;
	}
}

export function listJobStatusFiles(home = os.homedir()): string[] {
	const root = jobsRoot(home);
	try {
		return fs
			.readdirSync(root)
			.filter((name) => name.endsWith(".status.json"))
			.map((name) => path.join(root, name));
	} catch {
		return [];
	}
}
