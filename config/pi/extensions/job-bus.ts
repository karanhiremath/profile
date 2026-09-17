/**
 * Job bus: watch fire-and-forget job status files and steer the implementor.
 *
 * Inbox is per-session (~/.pi/agent/jobs/sessions/<sid>). Named lanes are
 * per-project (~/.pi/agent/jobs/projects/<slug>/streams/<name>). Subscribe
 * with the job_bus tool, PI_JOB_BUS_SUBSCRIBE, or (pi sessions only)
 * job-bus.json subscriptions. Bare "subagent" means this session's project
 * only. Use project:NAME/LANE or global:LANE for a foreign/host bus.
 * Cursor sessions watch their own inbox; they do not inherit host-global lanes.
 * Cross-session messages must set targetSid / PI_JOB_BUS_TARGET_SID.
 * Never poll the host-global jobs root unless subscribed to "legacy".
 */
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Text } from "@earendil-works/pi-tui";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";
import { Type } from "typebox";
import {
	ackPaths,
	isAcked,
	loadAck,
	pendingPaths,
	saveAck,
	type AckState,
} from "./lib/job-bus-ack.ts";
import {
	classifyDelivery,
	configuredSubscriptions,
	formatPointerBatch,
	type JobRecord,
} from "./lib/job-bus-target.ts";
import { projectSlug, watchDirsForSubscriptions } from "./lib/job-bus-project.ts";
import { emitJobOtel } from "./lib/agent-otel.ts";
import { tryInstantiateFromDisk, workspaceSummary, type InstantiatedWorkspace } from "./lib/fleet-workspace.ts";
import { listenUnix } from "./lib/stdio-socket.ts";
import { isolatedChildEnv } from "./subagent/pi-invocation.ts";
import type { Server } from "node:net";

const STATUS_ID = "job-bus";
const ENTRY_TYPE = "job-bus-board";
const WIDGET_LIMIT = 8;
const CONFIG_PATH = join(homedir(), ".pi", "agent", "job-bus.json");
const JOBS_ROOT = join(homedir(), ".pi", "agent", "jobs");
const DEFAULT_INTERVAL_MS = 2_000;
const CDEV_SESSION_BIN = (process.env.CDEV_SESSION_BIN || "").trim();

type Config = {
	enabled?: boolean;
	jobsDir?: string;
	scope?: "session" | "global";
	intervalMs?: number;
	autoSteer?: boolean;
	steerCursor?: boolean;
	steerHeartbeats?: boolean;
	implementorSid?: string;
	subscriptions?: string[];
};

const JobBusParams = Type.Object({
	action: StringEnum(["list", "subscribe", "unsubscribe", "mute", "unmute", "ack"] as const, {
		description:
			"list watched streams; subscribe/unsubscribe named lanes; mute/unmute auto-steer; ack seen job ids/cursors so poll stays quiet",
	}),
	streams: Type.Optional(
		Type.Array(Type.String(), {
			description:
				"Lane names are this session's project: assembler, cloudbuild, subagent. Foreign: project:NAME/LANE. Host-global opt-in: global:LANE, session:SID, unscoped, legacy",
		}),
	),
	jobIds: Type.Optional(
		Type.Array(Type.String(), {
			description: "Job ids this consumer has seen. Used with action=ack. Omit to ACK the current snapshot.",
		}),
	),
});

let timer: ReturnType<typeof setInterval> | undefined;
let boundInbox = "";
let boundSid = "";
let boundProject = "";
let runtimeSubs: string[] = [];
let ackState: AckState = { schema: "pi.job-bus-ack.v1", consumerId: "", ids: [], cursors: {} };
let boundWorkspace: InstantiatedWorkspace | undefined;
let commsServer: Server | undefined;

function safeSessionId(raw: string): string {
	return raw.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 128);
}

function resolveSessionId(ctx: ExtensionContext): string {
	for (const key of ["PI_SESSION_ID", "CDEV_SESSION_STEER_SID", "CDEV_SESSION_ID"]) {
		const value = (process.env[key] || "").trim();
		if (value) return safeSessionId(value);
	}
	const file = (
		ctx.sessionManager as { getSessionFile?: () => string | undefined } | undefined
	)?.getSessionFile?.();
	if (file) return safeSessionId(basename(file).replace(/\.jsonl$/, ""));
	return `pid-${process.pid}`;
}

function readConfigFile(): Config {
	try {
		return JSON.parse(readFileSync(CONFIG_PATH, "utf8")) as Config;
	} catch {
		return {};
	}
}

function subscriptionsFile(): string {
	return join(boundInbox || JOBS_ROOT, ".subscriptions.json");
}

function steerFile(): string {
	return join(boundInbox || JOBS_ROOT, ".steer.json");
}

function envFlag(name: string): string {
	return (process.env[name] || "").trim().toLowerCase();
}

function flagEnabled(raw: string): boolean | undefined {
	if (["0", "false", "no", "off"].includes(raw)) return false;
	if (["1", "true", "yes", "on"].includes(raw)) return true;
	return undefined;
}

function isCursorSession(): boolean {
	const agent = flagEnabled(envFlag("CURSOR_AGENT"));
	if (agent !== undefined) return agent;
	return Boolean((process.env.CURSOR_CONVERSATION_ID || "").trim());
}

function loadSessionSteer(): Pick<Config, "autoSteer"> {
	try {
		const data = JSON.parse(readFileSync(steerFile(), "utf8")) as { autoSteer?: boolean };
		return { autoSteer: data.autoSteer };
	} catch {
		return {};
	}
}

function saveSessionSteer(autoSteer: boolean): void {
	if (!boundInbox) return;
	mkdirSync(boundInbox, { recursive: true });
	writeFileSync(steerFile(), `${JSON.stringify({ autoSteer }, null, 2)}\n`);
}

function loadRuntimeSubs(): string[] {
	try {
		const data = JSON.parse(readFileSync(subscriptionsFile(), "utf8")) as { streams?: string[] };
		return Array.isArray(data.streams) ? data.streams.map(String) : [];
	} catch {
		return [];
	}
}

function saveRuntimeSubs(streams: string[]): void {
	if (!boundInbox) return;
	mkdirSync(boundInbox, { recursive: true });
	writeFileSync(subscriptionsFile(), `${JSON.stringify({ streams, project: boundProject }, null, 2)}\n`);
}

function bindInbox(ctx: ExtensionContext): string {
	if (boundInbox) return boundInbox;
	const file = readConfigFile();
	const cursor = isCursorSession();
	const explicit = (process.env.PI_JOBS_DIR || file.jobsDir || "").trim();
	boundSid = resolveSessionId(ctx);
	if (!process.env.PI_SESSION_ID) process.env.PI_SESSION_ID = boundSid;
	if (explicit && !cursor) {
		boundInbox = explicit;
	} else {
		boundInbox = join(JOBS_ROOT, "sessions", boundSid);
		if (!cursor) {
			process.env.PI_JOBS_DIR = boundInbox;
			if (!process.env.PI_JOB_STREAM && !process.env.PI_JOB_STREAM_PATH) {
				process.env.PI_JOB_STREAM = join(
					homedir(),
					".pi",
					"agent",
					"job-watcher-streams",
					"sessions",
					`${boundSid}.jsonl`,
				);
			}
		} else {
			delete process.env.PI_JOBS_DIR;
			if (!process.env.PI_JOB_BUS_SESSION_INBOX) process.env.PI_JOB_BUS_SESSION_INBOX = "0";
			if (!process.env.PI_JOB_BUS_STEER_SELF) process.env.PI_JOB_BUS_STEER_SELF = "0";
		}
	}
	try {
		mkdirSync(boundInbox, { recursive: true });
	} catch {
		/* still poll */
	}
	runtimeSubs = loadRuntimeSubs();
	return boundInbox;
}

function bindProject(ctx: ExtensionContext): string {
	boundProject = projectSlug(ctx.cwd || process.cwd());
	return boundProject;
}

function configuredSubs(): string[] {
	const file = readConfigFile();
	const fromFile = Array.isArray(file.subscriptions) ? file.subscriptions.map(String) : [];
	const fromEnv = (process.env.PI_JOB_BUS_SUBSCRIBE || "")
		.split(",")
		.map((s) => s.trim())
		.filter(Boolean);
	const scope = (process.env.PI_JOB_BUS_SCOPE || file.scope || "session").trim();
	return configuredSubscriptions({
		cursor: isCursorSession(),
		fileSubs: fromFile,
		envSubs: fromEnv,
		runtimeSubs,
		scope,
	});
}

function resolveWatchDirs(): string[] {
	return watchDirsForSubscriptions({
		inboxDir: boundInbox || join(JOBS_ROOT, "unscoped"),
		jobsRoot: JOBS_ROOT,
		boundProject,
		subscriptions: configuredSubs(),
	});
}

function loadConfig(): Required<
	Pick<Config, "enabled" | "intervalMs" | "autoSteer" | "steerCursor" | "steerHeartbeats" | "implementorSid">
> {
	const file = readConfigFile();
	const session = loadSessionSteer();
	const steerEnv = flagEnabled(envFlag("PI_JOB_BUS_STEER_SELF"));
	const heartbeatEnv = flagEnabled(envFlag("PI_JOB_BUS_STEER_HEARTBEATS"));
	const cursorEnv = flagEnabled(envFlag("PI_JOB_BUS_STEER_CURSOR"));
	let autoSteer = file.autoSteer !== false;
	if (typeof session.autoSteer === "boolean") autoSteer = session.autoSteer;
	if (steerEnv !== undefined) autoSteer = steerEnv;
	return {
		enabled: file.enabled !== false,
		intervalMs: Number(process.env.PI_JOB_BUS_INTERVAL_MS || file.intervalMs || DEFAULT_INTERVAL_MS),
		autoSteer,
		steerCursor: cursorEnv ?? file.steerCursor === true,
		steerHeartbeats: heartbeatEnv ?? file.steerHeartbeats === true,
		implementorSid: process.env.PI_IMPLEMENTOR_SID || process.env.CDEV_SESSION_STEER_SID || file.implementorSid || "",
	};
}

function widgetLines(): string[] {
	const files = allStatusFiles();
	const recs = files.map(readRecord).filter((record): record is JobRecord => Boolean(record));
	const seen = new Set<string>();
	const unique = recs.filter((record) => {
		const key = record.jobId || "";
		if (!key || seen.has(key)) return false;
		seen.add(key);
		return true;
	});
	const running = unique.filter((record) => record.status === "running");
	const subs = configuredSubs();
	const label = subs.length ? ` +${subs.join(",")}` : "";
	const project = boundProject ? ` ${boundProject}` : "";
	const header = `job-bus${project} ${running.length} running / ${unique.length} jobs${label}`;
	const rows = running.slice(0, WIDGET_LIMIT).map((record) => {
		const stream = record.stream ? ` ${record.stream}` : "";
		const recProject = record.project && record.project !== boundProject ? ` ${record.project}` : "";
		return `  ${record.jobId} running${stream}${recProject}`;
	});
	if (running.length > WIDGET_LIMIT) rows.push(`  +${running.length - WIDGET_LIMIT} more running`);
	return [header, ...rows];
}

function renderUi(ctx: ExtensionContext | ExtensionCommandContext): void {
	if (!ctx.hasUI) return;
	const lines = widgetLines();
	const running = /\b([1-9]\d*) running\b/.test(lines[0] || "");
	ctx.ui.setStatus(STATUS_ID, lines[0] || "job-bus idle");
	ctx.ui.setWidget(STATUS_ID, lines, { placement: "belowEditor" });
}

function persistAck(): void {
	if (!boundInbox || !ackState.consumerId) return;
	saveAck(boundInbox, ackState);
}

function ackPathLabel(): string {
	return boundInbox ? `${boundInbox}/.ack.json` : "(unbound)";
}

function reloadAck(): void {
	ackState = loadAck(boundInbox, boundSid || "unknown");
	if (!ackState.consumerId) ackState.consumerId = boundSid;
}

function ackCurrentSnapshot(): void {
	reloadAck();
	ackState = ackPaths(ackState, allStatusFiles(), (path) => readRecord(path) || {});
	persistAck();
}

function ackJobIds(jobIds: string[]): void {
	reloadAck();
	const wanted = new Set(jobIds.map((id) => id.trim()).filter(Boolean));
	const files = allStatusFiles().filter((file) => {
		const rec = readRecord(file);
		const jobId = rec?.jobId || file.replace(/\.status\.json$/, "").split("/").pop() || "";
		return wanted.has(jobId);
	});
	ackState = ackPaths(ackState, files.length ? files : [], (path) => readRecord(path) || {});
	for (const id of wanted) {
		if (!ackState.ids.includes(id)) ackState.ids.push(id);
	}
	persistAck();
}

function listStatusFiles(dir: string): string[] {
	try {
		return readdirSync(dir)
			.filter((name) => name.endsWith(".status.json"))
			.map((name) => join(dir, name));
	} catch {
		return [];
	}
}

function allStatusFiles(): string[] {
	return resolveWatchDirs().flatMap(listStatusFiles);
}

function readRecord(path: string): JobRecord | undefined {
	try {
		return JSON.parse(readFileSync(path, "utf8")) as JobRecord;
	} catch {
		return undefined;
	}
}

function steerCdev(sid: string, text: string): void {
	if (!sid || !existsSync(CDEV_SESSION_BIN)) return;
	const child = spawn(CDEV_SESSION_BIN, ["steer", sid, text], {
		stdio: "ignore",
		detached: true,
		env: isolatedChildEnv(),
	});
	child.unref();
}

function steerPi(pi: ExtensionAPI, text: string): void {
	const send = (pi as ExtensionAPI & {
		sendMessage?: (msg: unknown, opts?: unknown) => void;
	}).sendMessage;
	if (typeof send !== "function") return;
	// sendMessage participates in LLM context. Never fall back to sendUserMessage.
	send({ customType: STATUS_ID, content: text, display: true }, { triggerTurn: true, deliverAs: "followUp" });
}

function poll(pi: ExtensionAPI, ctx: ExtensionContext): void {
	const config = loadConfig();
	if (!config.enabled) return;
	reloadAck();
	const files = pendingPaths(ackState, allStatusFiles(), (path) => readRecord(path) || {});
	const steered = new Set<string>();
	const delivered: string[] = [];
	const steers: JobRecord[] = [];
	let steerSelf = false;
	for (const file of files) {
		const record = readRecord(file);
		if (!record) continue;
		if (isAcked(ackState, file, record)) continue;
		delivered.push(file);
		const delivery = classifyDelivery({
			autoSteer: config.autoSteer,
			cursor: isCursorSession(),
			steerCursor: config.steerCursor,
			boundSid,
			inboxDir: boundInbox,
			filePath: file,
			record,
			steerHeartbeats: config.steerHeartbeats,
			implementorSid: config.implementorSid,
			boundProject,
		});
		if (delivery.kind !== "steer") continue;
		const key = `${record.jobId || file}|${record.type || ""}|${record.status || ""}`;
		if (steered.has(key)) continue;
		steered.add(key);
		steers.push(record);
		if (delivery.self) steerSelf = true;
	}
	if (steers.length) {
		const text = formatPointerBatch(steers);
		if (config.implementorSid && config.implementorSid !== boundSid) {
			steerCdev(config.implementorSid, text);
		}
		if (steerSelf) steerPi(pi, text);
		for (const record of steers) {
			emitJobOtel("fleet.job.steered", {
				runtime: isCursorSession() ? "cursor" : "pi",
				session_id: boundSid,
				project: record.project || boundProject,
				job_id: record.jobId,
				stream: record.stream,
				status: record.status,
				summary: text,
				raw_ref: record.statusPath,
				privacy_domain: boundWorkspace?.privacy_domain,
			});
		}
	}
	if (delivered.length) {
		ackState = ackPaths(ackState, delivered, (path) => readRecord(path) || {});
		persistAck();
	}
	renderUi(ctx);
}

function listText(): string {
	const dirs = resolveWatchDirs();
	const files = allStatusFiles();
	const rows = files.map((file) => {
		const rec = readRecord(file);
		return `| ${rec?.jobId || basename(file)} | ${rec?.project || ""} | ${rec?.stream || ""} | ${rec?.status || ""} | ${rec?.source || ""} |`;
	});
	const config = loadConfig();
	const inboxFlag = process.env.PI_JOB_BUS_SESSION_INBOX || (isCursorSession() ? "0" : "1");
	return [
		`inbox: ${boundInbox}`,
		`project: ${boundProject || "(unbound)"}`,
		`steer self: ${config.autoSteer && !(isCursorSession() && !config.steerCursor) ? "on" : "off"}`,
		`cursor: ${isCursorSession() ? "yes" : "no"}`,
		`session inbox writes: ${inboxFlag}`,
		`ack: ${ackPathLabel()} (${ackState.ids.length} ids)`,
		`subscriptions: ${configuredSubs().join(", ") || "(none — own inbox only)"}`,
		`watch dirs:\n${dirs.map((d) => `- ${d}`).join("\n")}`,
		"",
		"| job | project | stream | status | source |",
		"|---|---|---|---|---|",
		...(rows.length ? rows : ["| (none) | | | | |"]),
		"",
		"Subscribe: job_bus action=subscribe streams=[\"subagent\"] (this project only). Foreign: project:NAME/LANE. Host-global: global:LANE, session:SID, unscoped, legacy.",
		"Named lanes update the TUI widget only. Model inject is one pointer on inbox/targeted terminal finish/fail.",
		"ACK seen jobs: job_bus action=ack jobIds=[\"job-id\"] (omit jobIds to ACK the current snapshot).",
		"Mute this session: job_bus action=mute (unmute to restore auto-steer).",
		"UI board (not sent to the model): /jobs",
		workspaceSummary(boundWorkspace),
	].join("\n");
}

export default function (pi: ExtensionAPI) {
	pi.registerEntryRenderer<{ lines?: string[]; ts?: string }>(ENTRY_TYPE, (entry) => {
		const lines = entry.data?.lines || ["job-bus idle"];
		return new Text(lines.join("\n"), 0, 0);
	});

	pi.registerCommand("jobs", {
		description: "Show the job-bus dashboard in the TUI (not sent to the model)",
		handler: async (_args, ctx) => {
			bindInbox(ctx as ExtensionContext);
			bindProject(ctx as ExtensionContext);
			reloadAck();
			const lines = widgetLines();
			renderUi(ctx);
			pi.appendEntry(ENTRY_TYPE, { lines, ts: new Date().toISOString() });
			if (ctx.hasUI) ctx.ui.notify(lines[0] || "job-bus idle", "info");
		},
	});

	pi.registerTool({
		name: "job_bus",
		label: "Job bus",
		description:
			"List, subscribe, ack, or mute this session on project-scoped job-bus streams. Bare lane names are this session's project only. Default poll is new messages after ACK. Named lanes are TUI dashboards. Model inject is one pointer sendMessage on inbox/targeted terminal finish/fail. Cursor sessions stay inbox-only.",
		parameters: JobBusParams,
		async execute(_toolCallId, params) {
			const streams = (params.streams || []).map((s) => s.trim()).filter(Boolean);
			if (params.action === "subscribe") {
				runtimeSubs = [...new Set([...runtimeSubs, ...streams])];
				saveRuntimeSubs(runtimeSubs);
				ackCurrentSnapshot();
				return { content: [{ type: "text", text: listText() }] };
			}
			if (params.action === "unsubscribe") {
				const drop = new Set(streams);
				runtimeSubs = runtimeSubs.filter((s) => !drop.has(s));
				saveRuntimeSubs(runtimeSubs);
				return { content: [{ type: "text", text: listText() }] };
			}
			if (params.action === "ack") {
				const ids = (params.jobIds || []).map((id) => id.trim()).filter(Boolean);
				if (ids.length) ackJobIds(ids);
				else ackCurrentSnapshot();
				return { content: [{ type: "text", text: listText() }] };
			}
			if (params.action === "mute") {
				saveSessionSteer(false);
				return { content: [{ type: "text", text: listText() }] };
			}
			if (params.action === "unmute") {
				saveSessionSteer(true);
				return { content: [{ type: "text", text: listText() }] };
			}
			return { content: [{ type: "text", text: listText() }] };
		},
	});

	pi.on("session_start", async (_event, ctx) => {
		if (timer) clearInterval(timer);
		if (commsServer) {
			commsServer.close();
			commsServer = undefined;
		}
		boundInbox = "";
		boundSid = "";
		boundProject = "";
		boundWorkspace = undefined;
		ackState = { schema: "pi.job-bus-ack.v1", consumerId: "", ids: [], cursors: {} };
		bindInbox(ctx);
		bindProject(ctx);
		reloadAck();
		boundWorkspace = tryInstantiateFromDisk();
		if (boundWorkspace?.ok) {
			if (!process.env.PI_AGENT_OTEL) process.env.PI_AGENT_OTEL = "1";
			if (boundWorkspace.otel_file && !process.env.PI_AGENT_OTEL_FILE) {
				process.env.PI_AGENT_OTEL_FILE = boundWorkspace.otel_file;
			}
			const commsOff = ["0", "false", "off"].includes((process.env.PI_FLEET_COMMS || "").toLowerCase());
			if (boundWorkspace.unix_socket && !commsOff) {
				try {
					commsServer = listenUnix(boundWorkspace.unix_socket);
				} catch {
					/* socket is best-effort */
				}
			}
			emitJobOtel("fleet.workspace.instantiated", {
				runtime: isCursorSession() ? "cursor" : "pi",
				session_id: boundSid,
				project: boundProject,
				summary: `fleet=${boundWorkspace.fleet}`,
				privacy_domain: boundWorkspace.privacy_domain,
			});
		}
		// History is the TUI board. Never replay existing files into the model on bind.
		ackCurrentSnapshot();
		const config = loadConfig();
		if (!config.enabled) return;
		poll(pi, ctx);
		timer = setInterval(() => poll(pi, ctx), config.intervalMs);
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		if (timer) clearInterval(timer);
		timer = undefined;
		if (commsServer) {
			commsServer.close();
			commsServer = undefined;
		}
		if (ctx.hasUI) {
			ctx.ui.setStatus(STATUS_ID, "");
			ctx.ui.setWidget(STATUS_ID, "");
		}
	});
}
