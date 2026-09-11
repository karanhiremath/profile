/**
 * Cross-session nudge for interrupted / Cursor-SDK-failed herm-tui panes
 * and Hermes subagents. Uses the existing atop / fleet_comms / steer-inbox
 * contract — not a second bus. One lock holder polls; each target is
 * steered via $HERMES_HOME/steer-inbox (and CONTROL when the heartbeat
 * advertises a port).
 */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, unlinkSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { emitJobOtel } from "./lib/agent-otel.ts";
import {
	classifyFailure,
	inferredSocketPath,
	isHermesSeat,
	isProtectedSeat,
	listHeartbeats,
	postHermesM2M,
	recoveryPrompt,
	tryAcquireLock,
	writeHermesInbox,
	type FailureKind,
	type HermesIdentity,
} from "./lib/hermes-steer.ts";

const STATUS_ID = "fleet-nudge";
const LOCK = join(homedir(), ".pi", "agent", "fleet-nudge.lock");
const CONFIG = join(homedir(), ".pi", "agent", "fleet-nudge.json");
const DEFAULT_INTERVAL_MS = 250;
const MIN_INTERVAL_MS = 5;
const CAPTURE_EVERY_MS = 250;
const COOLDOWN_MS = 15_000;

type Config = {
	enabled?: boolean;
	intervalMs?: number;
};

let timer: ReturnType<typeof setInterval> | undefined;
let lastCaptureAt = 0;
let holdLock = false;
const lastNudge = new Map<string, number>();

function envOff(name: string): boolean {
	return ["0", "false", "no", "off"].includes(String(process.env[name] || "").trim().toLowerCase());
}

function loadConfig(): { enabled: boolean; intervalMs: number } {
	let file: Config = {};
	try {
		file = JSON.parse(readFileSync(CONFIG, "utf8")) as Config;
	} catch {
		/* optional */
	}
	if (envOff("PI_FLEET_NUDGE") || file.enabled === false) {
		return { enabled: false, intervalMs: DEFAULT_INTERVAL_MS };
	}
	const raw = Number(process.env.PI_FLEET_NUDGE_INTERVAL_MS || file.intervalMs || DEFAULT_INTERVAL_MS);
	return { enabled: true, intervalMs: Math.max(MIN_INTERVAL_MS, Number.isFinite(raw) ? raw : DEFAULT_INTERVAL_MS) };
}

function acquireLock(): boolean {
	if (!tryAcquireLock(LOCK, process.pid)) return false;
	holdLock = true;
	return true;
}

function releaseLock(): void {
	if (!holdLock) return;
	try {
		const prev = JSON.parse(readFileSync(LOCK, "utf8")) as { pid?: number };
		if (prev.pid === process.pid) unlinkSync(LOCK);
	} catch {
		/* gone */
	}
	holdLock = false;
}

function tmuxPanes(): Array<{ target: string; pid: string; cmd: string; title: string }> {
	const out = spawnSync(
		"tmux",
		[
			"list-panes",
			"-a",
			"-F",
			"#{session_name}:#{window_index}.#{pane_index}\t#{pane_pid}\t#{pane_current_command}\t#{pane_title}",
		],
		{ encoding: "utf8", timeout: 1500 },
	);
	if (out.status !== 0) return [];
	return (out.stdout || "")
		.split("\n")
		.map((line) => line.split("\t"))
		.filter((p) => p.length >= 3)
		.map((p) => ({ target: p[0], pid: p[1], cmd: p[2], title: p[3] || "" }));
}

function fallbackHome(target: string, beats: HermesIdentity[]): string {
	const session = target.split(":")[0] || "";
	const hit = beats.find((beat) => (beat.tmux_target || "").split(":")[0] === session && beat.hermes_home);
	if (hit?.hermes_home) return hit.hermes_home;
	const cosw = join(
		homedir(),
		".local/share/hermes-agents/chief-of-staff-work/profiles/chief-of-staff-work",
	);
	if (/^cosw/i.test(session) && existsSync(join(cosw, "steer-inbox", "live"))) return cosw;
	return join(homedir(), ".hermes");
}

function capture(target: string): string {
	const out = spawnSync("tmux", ["capture-pane", "-t", target, "-p", "-J", "-S", "-80"], {
		encoding: "utf8",
		timeout: 1500,
	});
	return out.status === 0 ? out.stdout || "" : "";
}

function controlPost(port: number, mode: "steer" | "nudge", text: string): void {
	if (!port) return;
	const path = mode === "nudge" ? "/nudge" : "/steer";
	const child = spawnSync(
		"curl",
		[
			"-sS",
			"-m",
			"2",
			"-X",
			"POST",
			"-H",
			"Content-Type: application/json",
			"--data",
			JSON.stringify({ text }),
			`http://127.0.0.1:${port}${path}`,
		],
		{ encoding: "utf8", timeout: 2500 },
	);
	void child.status;
}

function nudgeTarget(ident: HermesIdentity, kind: FailureKind, sid: string): void {
	const now = Date.now();
	const prev = lastNudge.get(sid) || 0;
	if (now - prev < COOLDOWN_MS) return;
	lastNudge.set(sid, now);
	const text = recoveryPrompt(kind);
	const notes: string[] = [];
	let delivered = false;
	const sock = inferredSocketPath(ident);
	if (sock) {
		try {
			const reply = postHermesM2M(sock, "nudge", text);
			notes.push(`m2m ${sock} -> ${reply.status}`);
			delivered = reply.delivered || reply.status === "queued" || reply.status === "submitted";
		} catch (error) {
			notes.push(error instanceof Error ? error.message : String(error));
		}
	}
	if (!delivered && ident.control_port) {
		controlPost(ident.control_port, "nudge", text);
		notes.push(`CONTROL :${ident.control_port}`);
		delivered = true;
	}
	try {
		const paths = writeHermesInbox(ident, text, { mode: "nudge", sid, source: "fleet-nudge" });
		notes.push(`inbox ${paths.join(",")}`);
	} catch (error) {
		notes.push(error instanceof Error ? error.message : String(error));
	}
	emitJobOtel("fleet.nudge.result", {
		runtime: "hermes",
		session_id: sid,
		status: delivered ? "delivered" : "undelivered",
		summary: `${kind} ${sid}`,
		raw_ref: notes.join("; "),
	});
}

function poll(): void {
	const beats = listHeartbeats();
	const byPid = new Map(beats.map((b) => [String(b.pid), b]));
	const byTmux = new Map(beats.filter((b) => b.tmux_target).map((b) => [b.tmux_target, b]));
	const now = Date.now();
	const doCapture = now - lastCaptureAt >= CAPTURE_EVERY_MS;
	if (doCapture) lastCaptureAt = now;
	for (const pane of tmuxPanes()) {
		if (isProtectedSeat(pane.target)) continue;
		if (
			!isHermesSeat(pane.cmd, pane.title, pane.target) &&
			!byTmux.has(pane.target) &&
			!byPid.has(pane.pid)
		) {
			continue;
		}
		const fromPid = byPid.get(pane.pid);
		const fromTmux = byTmux.get(pane.target);
		const ident: HermesIdentity = fromPid ||
			(fromTmux && fromTmux.pid === pane.pid ? fromTmux : undefined) || {
				hermes_home: fromTmux?.hermes_home || fallbackHome(pane.target, beats),
				session_id: fromTmux?.session_id || "",
				control_port: fromTmux?.control_port || 0,
				pid: pane.pid,
				tmux_target: pane.target,
				socket_path: fromTmux?.pid === pane.pid ? fromTmux.socket_path : undefined,
			};
		if (!ident.tmux_target) ident.tmux_target = pane.target;
		if (!ident.pid) ident.pid = pane.pid;
		if (!doCapture) continue;
		const kind = classifyFailure(capture(pane.target));
		if (!kind) continue;
		nudgeTarget(ident, kind, ident.session_id || `tmux:${pane.target}`);
	}
}

export default function fleetNudgeMonitor(pi: ExtensionAPI): void {
	pi.registerCommand("fleet-nudge", {
		description: "Show herm-tui / Hermes fleet-nudge monitor status",
		handler: async (_args, ctx) => {
			const config = loadConfig();
			const text = [
				`enabled: ${config.enabled}`,
				`lock: ${holdLock ? `this-pid ${process.pid}` : existsSync(LOCK) ? readFileSync(LOCK, "utf8").trim() : "none"}`,
				`intervalMs: ${config.intervalMs} (min ${MIN_INTERVAL_MS}; capture every ${CAPTURE_EVERY_MS}ms)`,
				`heartbeats: ${listHeartbeats().length}`,
				"atop steer --harness hermes --sid tmux:SESSION:WIN.PANE --mode nudge --text '...'",
			].join("\n");
			if (ctx.hasUI) ctx.ui.notify(text.split("\n")[0] || "fleet-nudge", "info");
		},
	});

	const startWatch = (ctx?: ExtensionContext): void => {
		if (timer) return;
		const config = loadConfig();
		if (!config.enabled) return;
		if (!acquireLock()) return;
		poll();
		timer = setInterval(poll, config.intervalMs);
		if (ctx?.hasUI) ctx.ui.setStatus(STATUS_ID, "herm-tui nudge");
		emitJobOtel("fleet.nudge.attempt", {
			runtime: "pi",
			session_id: ctx?.sessionFile || "",
			status: "watching",
			summary: `interval=${config.intervalMs}ms`,
		});
	};

	pi.on("session_start", async (_event, ctx: ExtensionContext) => {
		if (timer) clearInterval(timer);
		timer = undefined;
		releaseLock();
		startWatch(ctx);
	});

	pi.on("turn_end", async (_event, ctx: ExtensionContext) => {
		startWatch(ctx);
	});

	pi.on("session_shutdown", async () => {
		if (timer) clearInterval(timer);
		timer = undefined;
		releaseLock();
	});
}

if (process.argv.includes("--watch")) {
	const config = loadConfig();
	if (config.enabled && acquireLock()) {
		try {
			poll();
		} catch (error) {
			process.stderr.write(`fleet-nudge first poll: ${error instanceof Error ? error.message : String(error)}\n`);
		}
		timer = setInterval(() => {
			try {
				poll();
			} catch (error) {
				process.stderr.write(`fleet-nudge poll: ${error instanceof Error ? error.message : String(error)}\n`);
			}
		}, config.intervalMs);
	} else {
		process.stderr.write("fleet-nudge --watch did not acquire lock or is disabled\n");
		process.exit(1);
	}
}
