/**
 * Probe primary harness remotes. Stubs stay stubs; never invent a steer path.
 */
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const HARNESS_NAMES = [
	"pi",
	"cursor",
	"claude-code",
	"codex",
	"hermes",
	"herdr",
	"cdev",
	"container",
	"devin",
] as const;
export type HarnessName = (typeof HARNESS_NAMES)[number];

export type HarnessProbe = {
	name: HarnessName;
	remote: "local" | "cdev" | "herdr" | "hermes" | "container" | "stub";
	status: "installed" | "stub" | "missing";
	steer?: string;
	discover?: string;
	note?: string;
	bin?: string;
	socket?: string;
};

function whichExists(path: string): boolean {
	return Boolean(path) && existsSync(path);
}

export function probeHarnesses(
	env: NodeJS.ProcessEnv = process.env,
	home = homedir(),
	names: HarnessName[] = [...HARNESS_NAMES],
): HarnessProbe[] {
	const probes: Record<HarnessName, HarnessProbe> = {
		pi: {
			name: "pi",
			remote: "cdev",
			status: existsSync(join(home, ".pi", "agent", "sessions")) ? "installed" : "missing",
			discover: join(home, ".pi", "agent", "sessions"),
			steer: "cdev session steer / job-bus sendMessage",
		},
		cursor: {
			name: "cursor",
			remote: "local",
			status: env.CURSOR_AGENT || env.CURSOR_CONVERSATION_ID || existsSync(join(home, ".cursor")) ? "stub" : "missing",
			note: "inbox-only job-bus; no cdev steer adapter yet",
		},
		"claude-code": {
			name: "claude-code",
			remote: "cdev",
			status: existsSync(join(home, ".claude", "projects")) ? "installed" : "missing",
			discover: join(home, ".claude", "projects"),
			steer: "cdev file-inbox / UserPromptSubmit hook",
		},
		codex: {
			name: "codex",
			remote: "stub",
			status: existsSync(join(home, ".codex")) ? "stub" : "missing",
			note: "inventory only until a steer surface exists",
			discover: join(home, ".codex"),
		},
		hermes: {
			name: "hermes",
			remote: "hermes",
			status: existsSync(join(home, ".hermes")) ? "installed" : "missing",
			steer: "CONTROL /steer|/nudge + $HERMES_HOME/steer-inbox; HTTP /v1/runs/{id}/steer for API runs",
			note: "herm-tui: mid-run-or-nudge; API run_id: mid-run tool boundary",
			discover: join(home, ".hermes"),
		},
		devin: {
			name: "devin",
			remote: "stub",
			status: "stub",
			note: "cloud harness; inventory stub",
		},
		herdr: {
			name: "herdr",
			remote: "herdr",
			status: env.HERDR_ENV === "1" || env.HERDR_SOCKET_PATH ? "installed" : "missing",
			socket: env.HERDR_SOCKET_PATH || "",
			steer: "herdr pane / AF_UNIX pane.report_agent",
		},
		cdev: {
			name: "cdev",
			remote: "cdev",
			status: "missing",
			steer: "cdev session steer",
		},
		container: {
			name: "container",
			remote: "container",
			status: "missing",
			note: "inject FLEET_COMMS_WS/SSE/TOKEN via Tailscale Serve",
		},
	};
	const cdevBin = String(env.CDEV_SESSION_BIN || "").trim();
	if (cdevBin) probes.cdev.bin = cdevBin;
	probes.cdev.status = cdevBin && whichExists(cdevBin) ? "installed" : "missing";
	return names.map((name) => probes[name]);
}

export function formatHarnessLines(probes: HarnessProbe[]): string[] {
	return probes.map((p) => `  ${p.name} ${p.status} remote=${p.remote}${p.note ? ` (${p.note})` : ""}`);
}
