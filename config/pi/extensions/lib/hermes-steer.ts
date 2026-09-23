/**
 * Hermes / herm-tui steer helpers. Twin of fleet_comms.steer hermes-tui
 * and herm-tui src/app/steer-inbox.ts. Writes $HERMES_HOME/steer-inbox
 * and classifies interrupted / Cursor-SDK failure text.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

export const STEER_SCHEMA = "harness-steer.v1";

export type FailureKind = "interrupted" | "cursor-sdk" | "subagent-failed";

export type HermesIdentity = {
	hermes_home: string;
	session_id: string;
	control_port: number;
	pid: string;
	tmux_target: string;
	socket_path?: string;
};

export type SteerRecord = {
	schema: typeof STEER_SCHEMA;
	text: string;
	mode: "steer" | "nudge";
	sid: string;
	subagent_id: string;
	ts: number;
	source: string;
};

export const HERMES_INTERRUPT_NUDGE =
	"Continue. The previous turn was interrupted or the Cursor SDK failed. Do not redo completed tools. Do not ask. If a hermes subagent is interrupted or failed, steer or continue that child.";

export function sanitizeInboxName(sid: string): string {
	return sid.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 128);
}

export function defaultHermesHome(home = homedir()): string {
	const env = String(process.env.HERMES_HOME || "").trim();
	if (env) return env;
	return join(home, ".hermes");
}

export function inboxPaths(ident: HermesIdentity): string[] {
	const root = join(ident.hermes_home, "steer-inbox");
	const out: string[] = [];
	if (ident.session_id) out.push(join(root, `${sanitizeInboxName(ident.session_id)}.jsonl`));
	if (ident.pid) out.push(join(root, `pid-${ident.pid}.jsonl`));
	if (ident.tmux_target) out.push(join(root, `tmux-${sanitizeInboxName(ident.tmux_target)}.jsonl`));
	return [...new Set(out)];
}

export function classifyFailure(text: string): FailureKind | null {
	const blob = text.toLowerCase();
	if (/\bsubagent\b/.test(blob) && /\b(failed|timeout|error|interrupted)\b/.test(blob)) {
		return "subagent-failed";
	}
	if (
		/operation interrupted|cursor[- ]?180|180\.0s|this operation was aborted|stopreason["\s:=]+aborted/.test(
			blob,
		)
	) {
		return "cursor-sdk";
	}
	if (/(^|\s)interrupted(\s|$)/.test(blob) || blob.includes("[interrupted]") || blob.includes("*interrupted*")) {
		return "interrupted";
	}
	return null;
}

export function recoveryPrompt(kind: FailureKind | null = "interrupted"): string {
	if (kind === "subagent-failed") {
		return `${HERMES_INTERRUPT_NUDGE} Prefer subagent.steer on the failed child.`;
	}
	return HERMES_INTERRUPT_NUDGE;
}

export function writeHermesInbox(
	ident: HermesIdentity,
	text: string,
	opts: { mode?: "steer" | "nudge"; sid?: string; source?: string } = {},
): string[] {
	const paths = inboxPaths(ident);
	if (!paths.length) throw new Error("no inbox target (need session_id, pid, or tmux_target)");
	const record: SteerRecord = {
		schema: STEER_SCHEMA,
		text,
		mode: opts.mode || "steer",
		sid: ident.session_id || opts.sid || "",
		subagent_id: "",
		ts: Date.now() / 1000,
		source: opts.source || "fleet-nudge",
	};
	const line = `${JSON.stringify(record)}\n`;
	for (const path of paths) {
		mkdirSync(dirname(path), { recursive: true });
		const existing = existsSync(path) ? readFileSync(path, "utf8") : "";
		writeFileSync(path, existing + line);
	}
	return paths;
}

export function inferredSocketPath(ident: HermesIdentity): string {
	const explicit = String(ident.socket_path || "").trim();
	if (explicit) return explicit;
	if (ident.pid) {
		const runtime = String(process.env.XDG_RUNTIME_DIR || "").trim() || "/tmp";
		return join(runtime, `herm-tui-${ident.pid}.sock`);
	}
	return "";
}

export function postHermesM2M(
	path: string,
	op: "steer" | "nudge" | "status" | "ping" | "approve",
	text = "",
): { ok: boolean; delivered: boolean; status: string; via: string } {
	const body = JSON.stringify(op === "approve" ? { op, choice: text, text } : { op, text });
	const child = spawnSync(
		"python3",
		["-c", "import json,socket,sys; p,b=sys.argv[1],sys.argv[2]; s=socket.socket(socket.AF_UNIX); s.settimeout(2); s.connect(p); s.sendall(b.encode()); s.shutdown(socket.SHUT_WR); print(s.recv(4096).decode())", path, body],
		{ encoding: "utf8", timeout: 3000 },
	);
	if (child.status !== 0) {
		throw new Error((child.stderr || child.stdout || "m2m failed").trim());
	}
	const parsed = JSON.parse((child.stdout || "").trim()) as {
		ok?: boolean;
		delivered?: boolean;
		status?: string;
		via?: string;
	};
	return {
		ok: Boolean(parsed.ok),
		delivered: Boolean(parsed.delivered),
		status: String(parsed.status || ""),
		via: String(parsed.via || "m2m"),
	};
}

export function processAlive(pid: number): boolean {
	try {
		process.kill(pid, 0);
		return true;
	} catch {
		return false;
	}
}

export function tryAcquireLock(
	lockPath: string,
	pid: number,
	now = Date.now(),
	alive: (p: number) => boolean = processAlive,
): boolean {
	try {
		mkdirSync(dirname(lockPath), { recursive: true });
		if (existsSync(lockPath)) {
			const raw = readFileSync(lockPath, "utf8").trim();
			if (raw) {
				try {
					const prev = JSON.parse(raw) as { pid?: number };
					if (typeof prev.pid === "number" && prev.pid !== pid && alive(prev.pid)) {
						return false;
					}
				} catch {
					/* corrupt lock is stealable */
				}
			}
		}
		writeFileSync(lockPath, `${JSON.stringify({ pid, ts: now })}\n`);
		return true;
	} catch {
		return false;
	}
}

export function isHermesSeat(cmd: string, title = "", target = ""): boolean {
	const blob = `${cmd} ${title}`.toLowerCase();
	if (
		blob.includes("herm-tui") ||
		blob.includes("tui_gateway") ||
		blob.includes("herm.cjs") ||
		blob.includes("index.tsx")
	) {
		return true;
	}
	const session = (target.split(":")[0] || "").toLowerCase();
	return /^cosw(-|$)/.test(session) && /^(bun|node)$/i.test(cmd.trim());
}

export function isProtectedSeat(target: string): boolean {
	const session = (target.split(":")[0] || "").toLowerCase();
	const pane = (target.split(":")[1] || "").split(".")[1] || "";
	if (/^cosw-yoshi$/.test(session)) return true;
	if (/^cosw-o[123]$/.test(session) && pane === "0") return true;
	if (/^cosw$/.test(session) && pane === "0") return true;
	return false;
}

function listDirs(path: string): string[] {
	try {
		return readdirSync(path, { withFileTypes: true })
			.filter((entry) => entry.isDirectory())
			.map((entry) => entry.name);
	} catch {
		return [];
	}
}

export function heartbeatRoots(home = homedir()): string[] {
	const roots = new Set<string>();
	roots.add(join(home, ".hermes"));
	const envHome = String(process.env.HERMES_HOME || "").trim();
	if (envHome) roots.add(envHome);
	const agents = join(home, ".local", "share", "hermes-agents");
	for (const agent of listDirs(agents)) {
		const profiles = join(agents, agent, "profiles");
		for (const profile of listDirs(profiles)) {
			roots.add(join(profiles, profile));
		}
	}
	return [...roots];
}

export function listHeartbeats(home = homedir()): HermesIdentity[] {
	const out: HermesIdentity[] = [];
	const seen = new Set<string>();
	for (const root of heartbeatRoots(home)) {
		const dir = join(root, "steer-inbox", "live");
		if (!existsSync(dir)) continue;
		for (const name of readdirSync(dir)) {
			if (!name.endsWith(".json")) continue;
			try {
				const raw = JSON.parse(readFileSync(join(dir, name), "utf8")) as Partial<HermesIdentity>;
				const ident: HermesIdentity = {
					hermes_home: String(raw.hermes_home || root),
					session_id: String(raw.session_id || ""),
					control_port: Number(raw.control_port || 0),
					pid: String(raw.pid || ""),
					tmux_target: String(raw.tmux_target || ""),
					socket_path: String((raw as { socket_path?: string }).socket_path || ""),
				};
				const pidNum = Number(ident.pid);
				if (ident.pid && Number.isFinite(pidNum) && pidNum > 0 && !processAlive(pidNum)) {
					continue;
				}
				const key = ident.pid || ident.tmux_target || `${root}:${name}`;
				if (seen.has(key)) continue;
				seen.add(key);
				out.push(ident);
			} catch {
				/* skip */
			}
		}
	}
	return out;
}

export function planHermesTransport(harness: string, sid: string): { transport: string; effective: string } {
	if (harness === "herm-tui" || sid.startsWith("tmux:") || sid.startsWith("proc:")) {
		return { transport: "hermes-tui", effective: "mid-run-or-nudge" };
	}
	if (harness === "hermes") {
		return { transport: "hermes-http", effective: "mid-run-tool-boundary" };
	}
	return { transport: "stub", effective: "none" };
}
